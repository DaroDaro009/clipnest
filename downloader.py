"""Native Windows desktop queue for creator profile downloads."""

from __future__ import annotations

import queue
import os
import shutil
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv", ".wmv", ".ts"}
PLATFORMS = ("tiktok", "youtube", "instagram")


def profile_url(platform: str, name: str) -> str:
    if platform not in PLATFORMS or not name or any(char in name for char in "/\\:@?&#"):
        raise ValueError(f"Invalid creator folder: {name}")
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{name}"
    if platform == "youtube":
        return f"https://www.youtube.com/@{name}/shorts"
    return f"https://www.instagram.com/{name}/"


def prepare_runtime() -> None:
    """Find bundled Node and FFmpeg without requiring installation on another PC."""
    vendor = Path(__file__).resolve().parent / ".vendor"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "binaries"
    if not bundled.is_dir():
        bundled = Path(__file__).resolve().parent / "src-tauri" / "binaries"
    if bundled.is_dir():
        os.environ["PATH"] = str(bundled) + os.pathsep + os.environ.get("PATH", "")


def video_count(folder: Path) -> int:
    count = 0
    try:
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                count += 1
    except OSError:
        pass
    return count


@dataclass(frozen=True)
class Job:
    row_id: str
    platform: str
    url: str
    folder: Path
    limit: int
    cookiefile: str
    cookies_text: str
    browser: str


class DownloadStopped(BaseException):
    pass


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        prepare_runtime()
        self.title("Clipnest")
        self.geometry("1040x720")
        self.minsize(790, 560)
        self.root_folder: Path | None = None
        self.folder_paths: dict[str, Path] = {}
        self.events: queue.Queue[tuple] = queue.Queue()
        self.busy = False
        self.stop_requested = threading.Event()
        self.root_label = tk.StringVar(value="Choose a root folder to begin")
        self.limit_value = tk.StringVar(value="10")
        self.workers_value = tk.StringVar(value="1")
        self.platform_value = tk.StringVar(value="youtube")
        self.browser_value = tk.StringVar(value="")
        self.cookiefile_value = tk.StringVar(value="")
        self.cookie_text_cache: dict[str, str] = {platform: "" for platform in PLATFORMS}
        self.cookie_settings: dict[str, dict[str, str]] = {}
        self.cookie_save_timer: str | None = None
        self.summary = tk.StringVar(value="Ready")
        self._build_ui()
        self._load_settings()
        self.after(100, self._process_events)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Clipnest", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Select creator folders, choose a platform, and download into those folders.").pack(anchor="w", pady=(0, 12))

        root_bar = ttk.Frame(outer)
        root_bar.pack(fill="x", pady=(0, 10))
        ttk.Button(root_bar, text="Choose root folder", command=self._choose_root).pack(side="left")
        ttk.Label(root_bar, textvariable=self.root_label).pack(side="left", padx=12)
        ttk.Button(root_bar, text="Rescan", command=self._scan_folders).pack(side="right")

        folders_frame = ttk.LabelFrame(outer, text="Creator folders — zero videos first", padding=8)
        folders_frame.pack(fill="both", expand=True)
        self.folders = ttk.Treeview(folders_frame, columns=("name", "count"), show="headings", selectmode="extended", height=8)
        self.folders.heading("name", text="Folder")
        self.folders.heading("count", text="Existing videos")
        self.folders.column("name", width=620, anchor="w")
        self.folders.column("count", width=140, anchor="center")
        self.folders.pack(side="left", fill="both", expand=True)
        folder_scroll = ttk.Scrollbar(folders_frame, orient="vertical", command=self.folders.yview)
        folder_scroll.pack(side="right", fill="y")
        self.folders.configure(yscrollcommand=folder_scroll.set)

        selection = ttk.Frame(outer)
        selection.pack(fill="x", pady=(6, 0))
        ttk.Button(selection, text="Select all", command=self._select_all).pack(side="left")
        ttk.Button(selection, text="Select under video limit", command=self._select_under_limit).pack(side="left", padx=6)
        ttk.Button(selection, text="Copy username", command=self._copy_username).pack(side="left")

        platform_row = ttk.Frame(outer)
        platform_row.pack(fill="x", pady=(12, 0))
        ttk.Label(platform_row, text="Platform:").pack(side="left")
        for platform, label in (("tiktok", "TikTok"), ("youtube", "YouTube Shorts"), ("instagram", "Instagram")):
            ttk.Radiobutton(platform_row, text=label, variable=self.platform_value, value=platform, command=self._change_platform).pack(side="left", padx=8)

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=10)
        ttk.Label(options, text="Videos per creator (0 = all):").pack(side="left")
        ttk.Entry(options, textvariable=self.limit_value, width=6).pack(side="left", padx=(6, 24))
        ttk.Label(options, text="Concurrent downloads:").pack(side="left")
        ttk.Entry(options, textvariable=self.workers_value, width=6).pack(side="left", padx=6)
        self.queue_button = ttk.Button(options, text="Download selected", command=self._add_to_queue)
        self.queue_button.pack(side="right")
        self.stop_button = ttk.Button(options, text="Stop downloads", command=self._stop, state="disabled")
        self.stop_button.pack(side="right", padx=8)

        cookies = ttk.LabelFrame(outer, text="Cookie settings (saved automatically for each platform)", padding=8)
        cookies.pack(fill="x", pady=(0, 10))
        cookie_top = ttk.Frame(cookies)
        cookie_top.pack(fill="x")
        ttk.Label(cookie_top, text="Browser:").pack(side="left")
        browser_box = ttk.Combobox(cookie_top, textvariable=self.browser_value, values=("", "chrome", "edge", "firefox"), state="readonly", width=10)
        browser_box.pack(side="left", padx=(5, 14))
        browser_box.bind("<<ComboboxSelected>>", self._schedule_cookie_save)
        ttk.Label(cookie_top, text="cookies.txt:").pack(side="left")
        cookie_entry = ttk.Entry(cookie_top, textvariable=self.cookiefile_value)
        cookie_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.cookiefile_value.trace_add("write", self._schedule_cookie_save)
        ttk.Button(cookie_top, text="Browse", command=self._browse_cookies).pack(side="left")
        ttk.Button(cookie_top, text="Clear", command=self._clear_cookies).pack(side="left", padx=(6, 0))
        ttk.Label(cookies, text="Or paste Netscape cookies.txt contents (stored encrypted for your Windows account):").pack(anchor="w", pady=(5, 2))
        self.cookies_text = tk.Text(cookies, height=2, wrap="none")
        self.cookies_text.pack(fill="x")
        self.cookies_text.bind("<KeyRelease>", self._schedule_cookie_save)

        queue_frame = ttk.LabelFrame(outer, text="Download queue", padding=8)
        queue_frame.pack(fill="both", expand=True)
        self.jobs = ttk.Treeview(queue_frame, columns=("folder", "title", "progress", "status"), show="headings", height=8)
        for column, heading, width in (("folder", "Creator", 190), ("title", "Current video / result", 410), ("progress", "Progress", 90), ("status", "Status", 170)):
            self.jobs.heading(column, text=heading)
            self.jobs.column(column, width=width, anchor="w")
        self.jobs.pack(side="left", fill="both", expand=True)
        job_scroll = ttk.Scrollbar(queue_frame, orient="vertical", command=self.jobs.yview)
        job_scroll.pack(side="right", fill="y")
        self.jobs.configure(yscrollcommand=job_scroll.set)
        self.jobs.bind("<<TreeviewSelect>>", self._show_job_detail)
        self.job_details: dict[str, str] = {}
        self.detail_label = ttk.Label(outer, text="Select a queue row to see its full status.", wraplength=970)
        self.detail_label.pack(anchor="w")
        ttk.Label(outer, textvariable=self.summary).pack(anchor="w", pady=(8, 0))

    def _choose_root(self) -> None:
        chosen = filedialog.askdirectory(title="Choose root folder")
        if chosen:
            import web_app
            self.root_folder = Path(chosen)
            self.root_label.set(str(self.root_folder))
            web_app.ROOT_STORE.write_text(chosen, encoding="utf-8")
            self._scan_folders()

    def _load_settings(self) -> None:
        import web_app

        try:
            saved_root = Path(web_app.ROOT_STORE.read_text(encoding="utf-8").strip())
            if saved_root.is_dir():
                self.root_folder = saved_root
                self.root_label.set(str(saved_root))
        except OSError:
            pass
        try:
            self.cookie_settings = web_app.load_cookie_settings()
        except (OSError, ValueError):
            self.cookie_settings = {}
        self._shown_platform = self.platform_value.get()
        self._show_cookies(self._shown_platform)
        self._scan_folders()

    def _show_cookies(self, platform: str) -> None:
        self._loading_cookies = True
        values = self.cookie_settings.get(platform, {})
        self.browser_value.set(values.get("browser", ""))
        self.cookiefile_value.set(values.get("cookiefile", ""))
        self.cookies_text.delete("1.0", "end")
        self.cookies_text.insert("1.0", values.get("cookies_text", ""))
        self._loading_cookies = False

    def _save_cookies(self) -> None:
        import web_app

        self.cookie_save_timer = None
        platform = self._shown_platform
        values = {
            "browser": self.browser_value.get(),
            "cookiefile": self.cookiefile_value.get().strip(),
            "cookies_text": self.cookies_text.get("1.0", "end-1c"),
        }
        try:
            web_app.save_cookie_settings(platform, **values)
            self.cookie_settings[platform] = values
        except (OSError, ValueError) as exc:
            self.summary.set(f"Could not save cookies: {exc}")

    def _schedule_cookie_save(self, *_args: object) -> None:
        if getattr(self, "_loading_cookies", False):
            return
        if self.cookie_save_timer:
            self.after_cancel(self.cookie_save_timer)
        self.cookie_save_timer = self.after(600, self._save_cookies)

    def _change_platform(self) -> None:
        if self.cookie_save_timer:
            self.after_cancel(self.cookie_save_timer)
        self._save_cookies()
        self._shown_platform = self.platform_value.get()
        self._show_cookies(self._shown_platform)

    def _browse_cookies(self) -> None:
        chosen = filedialog.askopenfilename(title="Choose cookies.txt", filetypes=(("Text files", "*.txt"), ("All files", "*.*")))
        if chosen:
            self.cookiefile_value.set(chosen)

    def _clear_cookies(self) -> None:
        self.browser_value.set("")
        self.cookiefile_value.set("")
        self.cookies_text.delete("1.0", "end")
        self._save_cookies()

    def _select_all(self) -> None:
        self.folders.selection_set(self.folders.get_children())

    def _select_under_limit(self) -> None:
        try:
            threshold = int(self.limit_value.get())
            if threshold <= 0:
                raise ValueError
        except ValueError:
            messagebox.showinfo("Video limit", "Enter a video limit greater than zero first.")
            return
        chosen = [row for row in self.folders.get_children() if int(self.folders.set(row, "count")) < threshold]
        self.folders.selection_set(chosen)
        self.summary.set(f"Selected {len(chosen)} folders with fewer than {threshold} videos.")

    def _copy_username(self) -> None:
        selected = self.folders.selection()
        if not selected:
            messagebox.showinfo("Copy username", "Select a creator folder first.")
            return
        name = self.folders.set(selected[0], "name")
        self.clipboard_clear()
        self.clipboard_append(name)
        self.summary.set(f"Copied username: {name}")

    def _show_job_detail(self, _event: object = None) -> None:
        selected = self.jobs.selection()
        if selected:
            self.detail_label.configure(text=self.job_details.get(selected[0], ""))

    def _scan_folders(self) -> None:
        self.folders.delete(*self.folders.get_children())
        self.folder_paths.clear()
        if self.root_folder is None:
            return
        try:
            children = sorted(
                ((p, video_count(p)) for p in self.root_folder.iterdir() if p.is_dir() and not p.is_symlink()),
                key=lambda item: (item[1], item[0].name.casefold()),
            )
        except OSError as exc:
            messagebox.showerror("Folder error", str(exc))
            return
        for child, count in children:
            row_id = self.folders.insert("", "end", values=(child.name, count))
            self.folder_paths[row_id] = child
        self.summary.set(f"Found {len(children)} subfolders. Select one or more to download into.")

    def _add_to_queue(self) -> None:
        if self.busy:
            return
        selected = self.folders.selection()
        if not selected:
            messagebox.showinfo("Choose creator folders", "Select at least one creator folder.")
            return
        try:
            limit = int(self.limit_value.get())
            workers = int(self.workers_value.get())
            if limit < 0 or not 1 <= workers <= 8:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid settings", "Max videos must be 0 or more; concurrent downloads must be 1–8.")
            return
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            messagebox.showerror("Missing dependency", "Install dependencies first: python -m pip install -r requirements.txt")
            return
        self._save_cookies()
        platform = self.platform_value.get()
        cookie_settings = self.cookie_settings.get(platform, {})
        tasks = []
        for folder_id in selected:
            folder = self.folder_paths[folder_id]
            try:
                url = profile_url(platform, folder.name)
            except ValueError as exc:
                messagebox.showerror("Invalid creator folder", str(exc))
                return
            tasks.append((folder, url))
        jobs = []
        for folder, url in tasks:
            row = self.jobs.insert("", "end", values=(folder.name, "Waiting", "0%", "Queued"))
            self.job_details[row] = url
            jobs.append(Job(row, platform, url, folder, limit,
                             cookie_settings.get("cookiefile", ""),
                             cookie_settings.get("cookies_text", ""),
                             cookie_settings.get("browser", "")))
        self.busy = True
        self.stop_requested.clear()
        self.queue_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.summary.set(f"Queued {len(jobs)} creator folders.")
        threading.Thread(target=self._run_batch, args=(jobs, workers), daemon=True).start()

    def _stop(self) -> None:
        self.stop_requested.set()
        self.stop_button.configure(state="disabled")
        self.summary.set("Stopping active downloads and clearing waiting jobs…")

    def _run_batch(self, tasks: list[Job], workers: int) -> None:
        # The semaphore prevents pending work from starting after Stop is pressed.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(self._run_job, tasks))
        self.events.put(("batch_done", results))

    def _run_job(self, job: Job) -> str:
        if self.stop_requested.is_set():
            self.events.put(("status", job.row_id, "—", "Stopped"))
            return "Stopped"
        self.events.put(("status", job.row_id, "0%", "Starting"))
        temporary_cookie_path: Path | None = None
        saved_count = 0
        errors: list[str] = []
        try:
            import yt_dlp
            import web_app

            def check_stopped() -> None:
                if self.stop_requested.is_set():
                    raise DownloadStopped()

            class DownloadLogger:
                def debug(self, _message: str) -> None:
                    pass

                def warning(self, _message: str) -> None:
                    pass

                def error(self, message: str) -> None:
                    errors.append(str(message))

            def progress(data: dict) -> None:
                check_stopped()
                title = (data.get("info_dict") or {}).get("title")
                if title:
                    self.events.put(("title", job.row_id, str(title)))
                if data.get("status") == "downloading":
                    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                    downloaded = data.get("downloaded_bytes") or 0
                    percent = f"{downloaded / total * 100:.0f}%" if total else "…"
                    self.events.put(("status", job.row_id, percent, "Downloading"))
                elif data.get("status") == "finished":
                    self.events.put(("status", job.row_id, "100%", "Processing"))

            has_ffmpeg = shutil.which("ffmpeg") is not None
            options = {
                "outtmpl": str(job.folder / "%(title).180B [%(id)s].%(ext)s"),
                "format": "bestvideo*+bestaudio/best" if has_ffmpeg else "best[ext=mp4]/best",
                "merge_output_format": "mp4" if has_ffmpeg else None,
                "noplaylist": False,
                "playlistend": job.limit or None,
                "download_archive": str(job.folder / ".video-downloader-archive.txt"),
                "progress_hooks": [progress],
                "match_filter": lambda _info, **_kwargs: check_stopped(),
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": "only_download",
                "windowsfilenames": True,
                "logger": DownloadLogger(),
            }
            if job.platform == "youtube":
                options["js_runtimes"] = {"node": {}}
            if job.cookies_text:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", prefix="clipnest-cookies-", delete=False) as temp:
                    temp.write(job.cookies_text.replace("\r\n", "\n"))
                    temporary_cookie_path = Path(temp.name)
                options["cookiefile"] = str(temporary_cookie_path)
            elif job.cookiefile:
                options["cookiefile"] = job.cookiefile
            elif job.browser:
                options["cookiesfrombrowser"] = (job.browser,)

            class TitleNumberPP(yt_dlp.postprocessor.PostProcessor):
                def run(self, info: dict) -> tuple[list, dict]:
                    nonlocal saved_count
                    check_stopped()
                    if web_app.number_video_by_title(info, job.folder) is not None:
                        saved_count += 1
                    return [], info

            def run_download(download_options: dict, urls: list[str]) -> int:
                check_stopped()
                with yt_dlp.YoutubeDL(download_options) as downloader:
                    downloader.add_post_processor(TitleNumberPP(), when="after_move")
                    try:
                        result = downloader.download(urls)
                    except yt_dlp.utils.DownloadError as exc:
                        if job.platform != "tiktok" or "secondary user ID" not in str(exc):
                            raise
                        result = 1
                    if job.platform != "tiktok" or result == 0:
                        return result
                    self.events.put(("status", job.row_id, "0%", "Finding TikTok posts"))
                    try:
                        ids, _ = web_app.fetch_tiktok_embed(downloader, job.folder.name)
                    except Exception:
                        ids = []
                    if not ids:
                        try:
                            sec_uid, ids = web_app.fetch_tiktok_profile(downloader, job.folder.name)
                        except Exception:
                            sec_uid, ids = None, []
                        if not ids and sec_uid:
                            return downloader.download([f"tiktokuser:{sec_uid}"])
                    if not ids:
                        raise RuntimeError("TikTok could not list public posts for this creator. Refresh the saved cookies and try again.")
                    selected_ids = ids[:job.limit] if job.limit else ids
                    return downloader.download([
                        f"https://www.tiktok.com/@{job.folder.name}/video/{video_id}" for video_id in selected_ids
                    ])

            try:
                result = run_download(options, [job.url])
            except yt_dlp.utils.DownloadError as exc:
                if job.platform == "youtube" and "page needs to be reloaded" in str(exc).lower() and ("cookiefile" in options or "cookiesfrombrowser" in options):
                    self.events.put(("detail", job.row_id, "YouTube rejected saved cookies. Retrying public Shorts without cookies."))
                    errors.clear()
                    public_options = {key: value for key, value in options.items() if key not in ("cookiefile", "cookiesfrombrowser")}
                    result = run_download(public_options, [job.url])
                else:
                    raise
            if (job.platform == "youtube" and result != 0
                    and ("cookiefile" in options or "cookiesfrombrowser" in options)
                    and any("page needs to be reloaded" in error.lower() for error in errors)):
                self.events.put(("detail", job.row_id, "YouTube rejected saved cookies. Retrying public Shorts without cookies."))
                errors.clear()
                public_options = {key: value for key, value in options.items() if key not in ("cookiefile", "cookiesfrombrowser")}
                result = run_download(public_options, [job.url])
            check_stopped()
            status = "Done" if result == 0 else "Partial" if saved_count else "Failed"
            if result:
                detail = errors[-1] if errors else "No video was downloaded from this profile."
                self.events.put(("detail", job.row_id, detail))
            else:
                self.events.put(("detail", job.row_id, f"Saved {saved_count} video(s) from {job.url}"))
            self.events.put(("status", job.row_id, "100%" if result == 0 else "—", status))
            return status
        except DownloadStopped:
            self.events.put(("detail", job.row_id, "Download stopped. An unfinished video can resume on the next attempt."))
            self.events.put(("status", job.row_id, "—", "Stopped"))
            return "Stopped"
        except Exception as exc:
            if self.stop_requested.is_set():
                self.events.put(("status", job.row_id, "—", "Stopped"))
                return "Stopped"
            detail = str(exc).replace("\n", " ")
            self.events.put(("detail", job.row_id, detail))
            self.events.put(("title", job.row_id, detail[:100]))
            status = "Partial" if saved_count else "Failed"
            self.events.put(("status", job.row_id, "—", status))
            return status
        finally:
            if temporary_cookie_path:
                temporary_cookie_path.unlink(missing_ok=True)

    def _process_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "status":
                    _, row, progress, status = event
                    if self.jobs.exists(row):
                        self.jobs.set(row, "progress", progress)
                        self.jobs.set(row, "status", status)
                elif event[0] == "title":
                    _, row, title = event
                    if self.jobs.exists(row):
                        self.jobs.set(row, "title", title)
                elif event[0] == "detail":
                    _, row, detail = event
                    self.job_details[row] = detail
                    if row in self.jobs.selection():
                        self.detail_label.configure(text=detail)
                elif event[0] == "batch_done":
                    results = event[1]
                    self.busy = False
                    self.queue_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self._scan_folders()
                    self.summary.set(f"Finished: {results.count('Done')} done, {results.count('Partial')} partial, {results.count('Failed')} failed, {results.count('Stopped')} stopped.")
        except queue.Empty:
            pass
        self.after(100, self._process_events)


if __name__ == "__main__":
    DownloaderApp().mainloop()
