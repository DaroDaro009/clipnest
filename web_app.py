"""Local web server for the downloader UI. Run: python web_app.py"""

from __future__ import annotations

import json
import base64
import html
import mimetypes
import os
import queue
import re
import shutil
import tempfile
import sys
import threading
import time
import uuid
import webbrowser
import ctypes
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from downloader import VIDEO_EXTENSIONS


HERE = Path(__file__).resolve().parent
LOCAL_PACKAGES = HERE / ".vendor"
if LOCAL_PACKAGES.is_dir():
    sys.path.insert(0, str(LOCAL_PACKAGES))
STATIC = HERE / "web"
HOST = "127.0.0.1"
TAURI_MODE = os.environ.get("CLIPNEST_TAURI") == "1"
PORT = int(os.environ.get("CLIPNEST_PORT", "8766"))
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Clipnest" if getattr(sys, "frozen", False) else HERE
DATA_DIR.mkdir(parents=True, exist_ok=True)
COOKIE_STORE = DATA_DIR / ".clipnest-cookies.dat"
ROOT_STORE = DATA_DIR / ".clipnest-root.txt"
TIKTOK_ID_STORE = DATA_DIR / ".clipnest-tiktok-ids.json"
PLATFORMS = {"tiktok", "youtube", "instagram"}
BROWSERS = {"", "chrome", "edge", "firefox"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
RENAME_LOCK = threading.RLock()
COOKIE_LOCK = threading.RLock()
TIKTOK_ID_LOCK = threading.RLock()


def _protect_cookie_data(data: bytes, *, decrypt: bool = False) -> bytes:
    """Use Windows DPAPI so saved cookies can only be read by this Windows user."""
    if os.name != "nt":
        raise OSError("Encrypted cookie auto-save requires Windows.")

    class DataBlob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = DataBlob()
    crypto = ctypes.windll.crypt32
    method = crypto.CryptUnprotectData if decrypt else crypto.CryptProtectData
    method.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(DataBlob)]
    method.restype = ctypes.c_int
    if not method(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        local_free = ctypes.windll.kernel32.LocalFree
        local_free.argtypes = [ctypes.c_void_p]
        local_free.restype = ctypes.c_void_p
        local_free(ctypes.cast(result.data, ctypes.c_void_p))


def _empty_cookie_settings() -> dict:
    return {platform: {"cookiefile": "", "cookies_text": "", "browser": ""} for platform in PLATFORMS}


def load_cookie_settings() -> dict:
    with COOKIE_LOCK:
        if not COOKIE_STORE.is_file():
            return _empty_cookie_settings()
        raw = _protect_cookie_data(base64.b64decode(COOKIE_STORE.read_bytes()), decrypt=True)
        saved = json.loads(raw)
        settings = _empty_cookie_settings()
        for platform in PLATFORMS:
            item = saved.get(platform, {})
            settings[platform] = {key: str(item.get(key, "")) for key in ("cookiefile", "cookies_text", "browser")}
        return settings


def save_cookie_settings(platform: str, cookiefile: str, cookies_text: str, browser: str) -> None:
    if platform not in PLATFORMS or browser not in BROWSERS:
        raise ValueError("Invalid cookie settings.")
    if len(cookiefile) > 4000 or len(cookies_text) > 200_000:
        raise ValueError("Cookie settings are too large.")
    with COOKIE_LOCK:
        settings = load_cookie_settings()
        settings[platform] = {"cookiefile": cookiefile, "cookies_text": cookies_text, "browser": browser}
        plaintext = json.dumps(settings).encode("utf-8")
        encrypted = base64.b64encode(_protect_cookie_data(plaintext))
        pending = COOKIE_STORE.with_suffix(".tmp")
        pending.write_bytes(encrypted)
        pending.replace(COOKIE_STORE)


def load_tiktok_ids() -> dict[str, str]:
    with TIKTOK_ID_LOCK:
        try:
            saved = json.loads(TIKTOK_ID_STORE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            str(name).casefold(): str(sec_uid)
            for name, sec_uid in saved.items()
            if isinstance(name, str) and isinstance(sec_uid, str)
        }


def save_tiktok_id(username: str, sec_uid: str) -> None:
    if not re.fullmatch(r"MS4wLjABAAAA[\w-]{64}", sec_uid):
        return
    with TIKTOK_ID_LOCK:
        saved = load_tiktok_ids()
        saved[username.casefold()] = sec_uid
        pending = TIKTOK_ID_STORE.with_suffix(".tmp")
        pending.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        pending.replace(TIKTOK_ID_STORE)


def valid_username(name: str) -> bool:
    return bool(name and name not in {".", ".."} and name.rstrip(". ") == name and name.upper().split(".")[0] not in WINDOWS_RESERVED and SAFE_NAME.fullmatch(name))


def profile_url(platform: str, name: str) -> str:
    if platform not in PLATFORMS:
        raise ValueError("Choose TikTok, YouTube, or Instagram.")
    if not valid_username(name):
        raise ValueError(f"Folder '{name}' is not a valid creator username.")
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{name}"
    if platform == "youtube":
        return f"https://www.youtube.com/@{name}/shorts"
    return f"https://www.instagram.com/{name}/"


def _find_tiktok_sec_uid(value: object, username: str) -> str | None:
    """Find TikTok's internal creator ID in profile hydration JSON."""
    if isinstance(value, dict):
        unique_id = value.get("uniqueId") or value.get("unique_id")
        sec_uid = value.get("secUid") or value.get("sec_uid")
        if str(unique_id).casefold() == username.casefold() and isinstance(sec_uid, str):
            return sec_uid
        for child in value.values():
            found = _find_tiktok_sec_uid(child, username)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_tiktok_sec_uid(child, username)
            if found:
                return found
    return None


def _find_tiktok_video_ids(value: object, username: str, found: list[str] | None = None) -> list[str]:
    found = found if found is not None else []
    if isinstance(value, dict):
        item_list = value.get("itemList")
        if isinstance(item_list, list):
            for item in item_list:
                if not isinstance(item, dict):
                    continue
                author = item.get("author") or item.get("authorInfo") or {}
                author_name = author.get("uniqueId") or author.get("unique_id") if isinstance(author, dict) else None
                video_id = item.get("id") or item.get("aweme_id")
                if isinstance(video_id, str) and (not author_name or str(author_name).casefold() == username.casefold()) and video_id not in found:
                    found.append(video_id)
        for child in value.values():
            _find_tiktok_video_ids(child, username, found)
    elif isinstance(value, list):
        for child in value:
            _find_tiktok_video_ids(child, username, found)
    return found


def fetch_tiktok_profile(downloader: object, username: str) -> tuple[str | None, list[str]]:
    """Load profile hydration with a real browser TLS fingerprint."""
    from curl_cffi import requests

    cookies = {
        cookie.name: cookie.value
        for cookie in downloader.cookiejar
        if "tiktok.com" in (cookie.domain or "")
    }
    response = requests.get(
        f"https://www.tiktok.com/@{username}",
        impersonate="chrome",
        cookies=cookies,
        headers={"Accept-Language": "en-US,en;q=0.9"},
        timeout=25,
    )
    response.raise_for_status()
    for match in re.finditer(r"<script[^>]*>(.*?)</script>", response.text, flags=re.IGNORECASE | re.DOTALL):
        if "secUid" not in match.group(1) and "itemList" not in match.group(1):
            continue
        try:
            data = json.loads(html.unescape(match.group(1)))
        except (json.JSONDecodeError, TypeError):
            continue
        sec_uid = _find_tiktok_sec_uid(data, username)
        video_ids = _find_tiktok_video_ids(data, username)
        if sec_uid:
            save_tiktok_id(username, sec_uid)
        if sec_uid or video_ids:
            return sec_uid, video_ids
    return None, []


def fetch_tiktok_embed(downloader: object, username: str) -> tuple[list[str], bool]:
    """Get public post IDs from TikTok's creator embed when its profile is blocked."""
    from curl_cffi import requests

    cookies = {
        cookie.name: cookie.value
        for cookie in downloader.cookiejar
        if "tiktok.com" in (cookie.domain or "")
    }
    # TikTok sometimes challenges one request but serves the next, and an old
    # saved session can be blocked while the public embed still works.
    cookie_attempts = [cookies, cookies, {}, {}] if cookies else [{}, {}, {}, {}]
    for attempt, request_cookies in enumerate(cookie_attempts):
        if attempt:
            time.sleep(0.6 * attempt)
        try:
            response = requests.get(
                f"https://www.tiktok.com/embed/@{username}",
                impersonate="chrome",
                cookies=request_cookies,
                headers={"Accept-Language": "en-US,en;q=0.9"},
                timeout=25,
            )
            response.raise_for_status()
            match = re.search(
                r'<script[^>]+id=["\']__FRONTITY_CONNECT_STATE__["\'][^>]*>(.*?)</script>',
                response.text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not match:
                continue
            data = json.loads(html.unescape(match.group(1)))
            profile = data.get("source", {}).get("data", {}).get(f"/embed/@{username}", {})
            user = profile.get("userInfo") or {}
            if str(user.get("uniqueId", "")).casefold() != username.casefold():
                continue
            video_ids = []
            for item in profile.get("videoList") or []:
                video_id = str(item.get("id", "")) if isinstance(item, dict) else ""
                if re.fullmatch(r"\d{15,22}", video_id) and video_id not in video_ids:
                    video_ids.append(video_id)
            return video_ids, True
        except (requests.errors.RequestsError, json.JSONDecodeError, ValueError):
            continue
    return [], False


def resolve_tiktok_sec_uid(downloader: object, username: str) -> str | None:
    """Resolve a TikTok username when the stock profile extractor misses it."""
    from yt_dlp.networking import Request

    if cached := load_tiktok_ids().get(username.casefold()):
        return cached

    request = Request(
        f"https://www.tiktok.com/@{username}",
        headers={
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
            ),
        },
    )
    response = downloader.urlopen(request)
    webpage = response.read().decode("utf-8", "replace")
    for match in re.finditer(
        r'<script[^>]+id=["\'](?:__UNIVERSAL_DATA_FOR_REHYDRATION__|SIGI_STATE|sigi-persisted-data)["\'][^>]*>(.*?)</script>',
        webpage,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            data = json.loads(html.unescape(match.group(1)))
        except (json.JSONDecodeError, TypeError):
            continue
        if sec_uid := _find_tiktok_sec_uid(data, username):
            save_tiktok_id(username, sec_uid)
            return sec_uid
    return None


def number_video_by_title(info: dict, folder: Path) -> Path | None:
    """Rename a completed video to its title, numbering only repeated titles."""
    filepath = info.get("filepath")
    if not filepath:
        return None
    source = Path(filepath)
    if not source.is_file() or source.resolve().parent != folder.resolve():
        return None
    suffix = f" [{info.get('id', '')}]"
    stem = source.stem[:-len(suffix)] if source.stem.endswith(suffix) else source.stem
    stem = stem.strip() or "video"
    with RENAME_LOCK:
        number = 1
        while True:
            label = stem if number == 1 else f"{stem} ({number})"
            target = source.with_name(label + source.suffix)
            if target == source:
                break
            title_in_use = any(source.with_name(label + extension).exists() for extension in VIDEO_EXTENSIONS)
            if not title_in_use:
                try:
                    os.link(source, target)
                    source.unlink()
                    break
                except FileExistsError:
                    number += 1
                    continue
                except OSError:
                    # Some filesystems do not support hard links.
                    if target.exists():
                        number += 1
                        continue
                    source.rename(target)
                    break
            number += 1
    info["filepath"] = str(target)
    return target


@dataclass
class Download:
    id: str
    platform: str
    folder: str
    url: str
    status: str = "Queued"
    progress: float = 0
    detail: str = ""
    title: str = ""


class DownloadStopped(Exception):
    """Raised by yt-dlp hooks after the user stops the queue."""


class State:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        try:
            saved_root = Path(ROOT_STORE.read_text(encoding="utf-8").strip())
            self.root: Path | None = saved_root if saved_root.is_dir() else None
        except OSError:
            self.root = None
        self.jobs: list[Download] = []
        self.pending: queue.Queue[tuple[Download, int, str, str, str]] = queue.Queue()
        self.active = 0
        self.concurrency = 2
        self.stopping = False
        self.cancel_events: dict[str, threading.Event] = {}
        self.executor = ThreadPoolExecutor(max_workers=8)

    def folders(self) -> list[dict]:
        with self.lock:
            root = self.root
        if root is None:
            return []
        folders = []
        for child in root.iterdir():
            if child.is_dir() and not child.is_symlink() and not getattr(child, "is_junction", lambda: False)():
                count = sum(1 for p in child.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)
                folders.append({"name": child.name, "count": count, "valid": valid_username(child.name)})
        return sorted(folders, key=lambda item: (item["count"], item["name"].casefold()))

    def snapshot(self) -> dict:
        with self.lock:
            root = str(self.root) if self.root else None
            jobs = [asdict(job) for job in self.jobs]
            active = self.active
            pending = self.pending.qsize()
            stopping = self.stopping
        return {"root": root, "jobs": jobs, "active": active, "pending": pending, "stopping": stopping}

    def add(self, platform: str, names: list[str], limit: int, concurrency: int, cookiefile: str, cookies_text: str, browser: str) -> int:
        with self.lock:
            if not self.root:
                raise ValueError("Choose a root folder first.")
            if not names:
                raise ValueError("Select at least one creator folder.")
            root = self.root.resolve()
            creators = []
            for name in dict.fromkeys(names):
                url = profile_url(platform, name)
                destination = root / name
                if not destination.is_dir() or destination.is_symlink() or getattr(destination, "is_junction", lambda: False)() or destination.resolve().parent != root:
                    raise ValueError(f"Creator folder '{name}' is no longer available. Rescan folders.")
                creators.append((url, name))
            if limit < 0 or not 1 <= concurrency <= 8:
                raise ValueError("Use a video limit of 0 or more and concurrency from 1 to 8.")
            if cookiefile and not cookies_text and not Path(cookiefile).is_file():
                raise ValueError("The cookies file could not be found.")
            if cookies_text and not cookies_text.lstrip().startswith(("# HTTP Cookie File", "# Netscape HTTP Cookie File")):
                raise ValueError("Pasted cookies must be in Netscape cookies.txt format.")
            if browser not in BROWSERS:
                raise ValueError("Choose a supported browser for cookies.")
            try:
                import yt_dlp  # noqa: F401
            except ImportError as exc:
                raise ValueError("Install yt-dlp first: python -m pip install -r requirements.txt") from exc
            self.concurrency = concurrency
            self.stopping = False
            count = 0
            for url, name in creators:
                job = Download(str(uuid.uuid4()), platform, name, url)
                self.jobs.append(job)
                self.cancel_events[job.id] = threading.Event()
                self.pending.put((job, limit, cookiefile, cookies_text, browser))
                count += 1
            self._schedule()
            return count

    def _schedule(self) -> None:
        while not self.stopping and self.active < self.concurrency and not self.pending.empty():
            job, limit, cookiefile, cookies_text, browser = self.pending.get_nowait()
            if self.cancel_events[job.id].is_set():
                job.status = "Stopped"
                continue
            self.active += 1
            job.status = "Starting"
            self.executor.submit(self._download, job, limit, cookiefile, cookies_text, browser)

    def _download(self, job: Download, limit: int, cookiefile: str, cookies_text: str, browser: str) -> None:
        temporary_cookie_path: Path | None = None
        cancel_event = self.cancel_events[job.id]
        try:
            import yt_dlp

            with self.lock:
                assert self.root is not None
                destination = self.root / job.folder
            finished_count = 0
            fallback_attempted = False
            retry_without_cookies = False
            def check_stopped() -> None:
                if cancel_event.is_set():
                    raise DownloadStopped()

            def progress(data: dict) -> None:
                nonlocal finished_count
                check_stopped()
                with self.lock:
                    title = (data.get("info_dict") or {}).get("title")
                    if title:
                        job.title = str(title)
                    if data.get("status") == "downloading":
                        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                        job.progress = round(100 * (data.get("downloaded_bytes") or 0) / total) if total else 0
                        job.status = "Downloading"
                    elif data.get("status") == "finished":
                        finished_count += 1
                        job.progress = 100
                        job.status = "Processing"

            def match_filter(info: dict, *, incomplete: bool = False) -> None:
                check_stopped()

            has_ffmpeg = shutil.which("ffmpeg") is not None
            options = {
                "outtmpl": str(destination / "%(title).180B [%(id)s].%(ext)s"),
                "format": "bestvideo*+bestaudio/best" if has_ffmpeg else "best[ext=mp4]/best",
                "merge_output_format": "mp4" if has_ffmpeg else None,
                "playlistend": limit or None,
                "download_archive": str(destination / ".video-downloader-archive.txt"),
                "progress_hooks": [progress],
                "match_filter": match_filter,
                "quiet": True,
                "no_warnings": True,
                "windowsfilenames": True,
            }
            if job.platform == "tiktok":
                options["user_agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
                )
            elif job.platform == "youtube":
                options["js_runtimes"] = {"node": {}}
            if cookies_text:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", prefix="clipnest-cookies-", delete=False) as temp:
                    temp.write(cookies_text.replace("\r\n", "\n"))
                    temporary_cookie_path = Path(temp.name)
                options["cookiefile"] = str(temporary_cookie_path)
            elif cookiefile:
                options["cookiefile"] = cookiefile
            elif browser:
                options["cookiesfrombrowser"] = (browser,)
            class TitleNumberPP(yt_dlp.postprocessor.PostProcessor):
                def run(self, info: dict) -> tuple[list, dict]:
                    check_stopped()
                    number_video_by_title(info, destination)
                    return [], info

            with yt_dlp.YoutubeDL(options) as downloader:
                downloader.add_post_processor(TitleNumberPP(), when="after_move")

                def download_tiktok_fallback() -> int:
                    with self.lock:
                        job.status = "Resolving TikTok profile"
                        job.detail = "Looking for public posts on TikTok's creator page."
                    check_stopped()
                    try:
                        embed_ids, embed_found = fetch_tiktok_embed(downloader, job.folder)
                    except Exception:
                        embed_ids, embed_found = [], False
                    check_stopped()
                    if embed_ids:
                        selected_ids = embed_ids[:limit] if limit else embed_ids
                        return downloader.download([
                            f"https://www.tiktok.com/@{job.folder}/video/{video_id}"
                            for video_id in selected_ids
                        ])
                    try:
                        sec_uid, video_ids = fetch_tiktok_profile(downloader, job.folder)
                    except Exception:
                        sec_uid, video_ids = None, []
                    check_stopped()
                    sec_uid = sec_uid or load_tiktok_ids().get(job.folder.casefold())
                    if video_ids:
                        selected_ids = video_ids[:limit] if limit else video_ids
                        return downloader.download([
                            f"https://www.tiktok.com/@{job.folder}/video/{video_id}"
                            for video_id in selected_ids
                        ])
                    if sec_uid:
                        try:
                            return downloader.download([f"tiktokuser:{sec_uid}"])
                        except yt_dlp.utils.DownloadError:
                            if not embed_found:
                                raise
                    if embed_found:
                        raise RuntimeError(
                            "TikTok's creator page currently shows no public videos for this account."
                        )
                    raise RuntimeError(
                        "TikTok blocked the creator page with a security challenge. "
                        "Open the profile in your browser, refresh its saved cookies, and try again."
                    )

                check_stopped()
                try:
                    result = downloader.download([job.url])
                except yt_dlp.utils.DownloadError as first_error:
                    if (job.platform == "youtube" and "page needs to be reloaded" in str(first_error).lower()
                            and any(key in options for key in ("cookiefile", "cookiesfrombrowser"))):
                        retry_without_cookies = True
                    elif job.platform == "tiktok" and "secondary user ID" in str(first_error):
                        fallback_attempted = True
                        result = download_tiktok_fallback()
                    else:
                        raise
                if job.platform == "tiktok" and result != 0 and not fallback_attempted:
                    fallback_attempted = True
                    result = download_tiktok_fallback()
                if job.platform == "tiktok" and result == 0 and finished_count == 0:
                    has_existing_video = any(
                        path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
                        for path in destination.rglob("*")
                    )
                    if not has_existing_video:
                        raise RuntimeError(
                            "TikTok returned no downloadable public videos for this creator."
                        )
                check_stopped()
            if retry_without_cookies:
                with self.lock:
                    job.status = "Starting"
                    job.detail = "YouTube rejected the saved cookies. Retrying public Shorts without cookies."
                public_options = {key: value for key, value in options.items()
                                  if key not in ("cookiefile", "cookiesfrombrowser")}
                with yt_dlp.YoutubeDL(public_options) as downloader:
                    downloader.add_post_processor(TitleNumberPP(), when="after_move")
                    check_stopped()
                    result = downloader.download([job.url])
                    check_stopped()
            with self.lock:
                job.status = "Done" if result == 0 else "Failed"
                job.progress = 100 if result == 0 else job.progress
                if result == 0:
                    job.detail = ""
        except DownloadStopped:
            with self.lock:
                job.status = "Stopped"
                job.detail = "Download stopped. An unfinished video can resume on the next attempt."
        except Exception as exc:
            with self.lock:
                if cancel_event.is_set():
                    job.status = "Stopped"
                    job.detail = "Download stopped. An unfinished video can resume on the next attempt."
                    return
                job.status = "Failed"
                detail = str(exc).replace("\n", " ")
                if job.platform == "tiktok" and ("secondary user ID" in detail or "does not have any videos posted" in detail):
                    detail = "TikTok profile could not be read. Try fresh browser cookies; yt-dlp may still fail on some profiles. " + detail
                elif job.platform == "tiktok" and "Failed to parse JSON" in detail:
                    detail = (
                        "TikTok did not return a usable video list. Open the profile in your browser, "
                        "then try again with refreshed cookies. " + detail
                    )
                job.detail = detail[:300]
        finally:
            if temporary_cookie_path:
                try:
                    temporary_cookie_path.unlink(missing_ok=True)
                except OSError:
                    pass
            with self.lock:
                self.active -= 1
                self.cancel_events.pop(job.id, None)
                self._schedule()

    def stop(self) -> None:
        with self.lock:
            self.stopping = True
            for job in self.jobs:
                event = self.cancel_events.get(job.id)
                if event and job.status in {"Starting", "Downloading", "Processing", "Resolving TikTok profile"}:
                    event.set()
                    job.status = "Stopping"
            while not self.pending.empty():
                job, _, _, _, _ = self.pending.get_nowait()
                self.cancel_events.pop(job.id, None)
                job.status = "Stopped"


STATE = State()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        if not TAURI_MODE and self.path not in {"/api/status", "/api/folders"}:
            super().log_message(format, *args)

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ValueError("Expected JSON request.")
        size = int(self.headers.get("Content-Length", "0"))
        if size > 256_000:
            raise ValueError("Request is too large.")
        return json.loads(self.rfile.read(size))

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        return not origin or origin == f"http://{HOST}:{self.server.server_address[1]}"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._json(STATE.snapshot())
            return
        if path == "/api/folders":
            try:
                self._json({"folders": STATE.folders(), "root": STATE.snapshot()["root"]})
            except OSError as exc:
                self._json({"error": str(exc)}, 400)
            return
        if path == "/api/cookies":
            try:
                self._json({"settings": load_cookie_settings()})
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": f"Saved cookies could not be opened: {exc}"}, 500)
            return
        file = STATIC / ("index.html" if path == "/" else path.lstrip("/"))
        if not file.is_file() or not file.resolve().is_relative_to(STATIC):
            self.send_error(404)
            return
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(file)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not self._same_origin():
            self._json({"error": "Request origin is not allowed."}, 403)
            return
        try:
            path = urlparse(self.path).path
            if path == "/api/choose-folder":
                with STATE.lock:
                    if STATE.active or not STATE.pending.empty():
                        raise ValueError("Wait for the current queue to finish before changing the root folder.")
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                chosen = filedialog.askdirectory(title="Choose download root folder", parent=root)
                root.destroy()
                if chosen:
                    with STATE.lock:
                        if STATE.active or not STATE.pending.empty():
                            raise ValueError("The queue started while choosing a folder. Try again when it finishes.")
                        STATE.root = Path(chosen)
                        ROOT_STORE.write_text(chosen, encoding="utf-8")
                self._json({"root": str(STATE.root) if STATE.root else None})
            elif path == "/api/choose-cookies":
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                chosen = filedialog.askopenfilename(title="Choose Netscape cookies file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")], parent=root)
                root.destroy()
                self._json({"path": chosen or None})
            elif path == "/api/queue":
                data = self._body()
                count = STATE.add(data.get("platform", ""), data.get("folders", []), int(data.get("limit", 10)), int(data.get("concurrency", 2)), data.get("cookiefile", ""), data.get("cookies_text", ""), data.get("browser", ""))
                self._json({"queued": count})
            elif path == "/api/cookies":
                data = self._body()
                save_cookie_settings(data.get("platform", ""), data.get("cookiefile", ""), data.get("cookies_text", ""), data.get("browser", ""))
                self._json({"saved": True})
            elif path == "/api/stop":
                STATE.stop()
                self._json({"ok": True})
            else:
                self._json({"error": "Unknown endpoint."}, 404)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, 400)


if __name__ == "__main__":
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        if TAURI_MODE:
            raise
        server = ThreadingHTTPServer((HOST, 0), Handler)
    address = f"http://{HOST}:{server.server_address[1]}"
    if not TAURI_MODE:
        print(f"Open {address}", flush=True)
        threading.Timer(0.5, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
