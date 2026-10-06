"""Clipnest's existing web layout in a self-contained Python desktop window."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

# Windows must find the bundled Qt DLLs before another application's Qt copy.
# Keep the directory handle alive for the entire process.
_qt_bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "PySide6"
_qt_dll_directory = os.add_dll_directory(str(_qt_bundle)) if os.name == "nt" and _qt_bundle.is_dir() else None
if _qt_dll_directory is not None:
    os.environ["PATH"] = str(_qt_bundle) + os.pathsep + os.environ.get("PATH", "")

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

import downloader
import web_app


WEB_DIR = Path(__file__).resolve().parent / "web"


class NativeState(web_app.State):
    """Keep the web UI's queue and folder model, using downloader.py for transfers."""

    def _download(self, job: web_app.Download, limit: int, cookiefile: str, cookies_text: str, browser: str) -> None:
        with self.lock:
            assert self.root is not None
            folder = self.root / job.folder
            cancel_event = self.cancel_events[job.id]

        state = self

        class EventSink:
            def put(self, event: tuple) -> None:
                kind = event[0]
                with state.lock:
                    if kind == "status":
                        progress, status = event[2], event[3]
                        if isinstance(progress, str) and progress.endswith("%"):
                            try:
                                job.progress = max(0, min(100, int(progress[:-1])))
                            except ValueError:
                                pass
                        job.status = "Resolving TikTok profile" if status == "Finding TikTok posts" else status
                    elif kind == "title":
                        job.title = event[2]
                    elif kind == "detail":
                        job.detail = event[2]

        engine = SimpleNamespace(events=EventSink(), stop_requested=cancel_event)
        work = downloader.Job(job.id, job.platform, job.url, folder, limit, cookiefile, cookies_text, browser)
        result = "Failed"
        try:
            result = downloader.DownloaderApp._run_job(engine, work)
        except BaseException as exc:
            with self.lock:
                job.detail = str(exc) or "The download stopped unexpectedly."
        finally:
            with self.lock:
                job.status = result
                self.active -= 1
                self.cancel_events.pop(job.id, None)
                self._schedule()


class DesktopPage(QWebEnginePage):
    def acceptNavigationRequest(self, url: QUrl, navigation_type, is_main_frame: bool) -> bool:
        if not is_main_frame:
            return True
        if url.isLocalFile():
            try:
                return Path(url.toLocalFile()).resolve().is_relative_to(WEB_DIR.resolve())
            except OSError:
                return False
        if navigation_type == QWebEnginePage.NavigationTypeLinkClicked and url.scheme() in {"https", "http"}:
            QDesktopServices.openUrl(url)
        return False


class DesktopBridge(QObject):
    def __init__(self, state: NativeState, window: QMainWindow) -> None:
        super().__init__(window)
        self.state = state
        self.window = window

    @Slot(str, str, str, result=str)
    def request(self, path: str, method: str, body: str) -> str:
        try:
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                raise ValueError("Invalid request.")
            if path == "folders" and method == "GET":
                result = {"folders": self.state.folders(), "root": self.state.snapshot()["root"]}
            elif path == "status" and method == "GET":
                result = self.state.snapshot()
            elif path == "cookies" and method == "GET":
                result = {"settings": web_app.load_cookie_settings()}
            elif path == "cookies" and method == "POST":
                web_app.save_cookie_settings(
                    data.get("platform", ""), data.get("cookiefile", ""),
                    data.get("cookies_text", ""), data.get("browser", ""),
                )
                result = {"saved": True}
            elif path == "choose-folder" and method == "POST":
                with self.state.lock:
                    if self.state.active or not self.state.pending.empty():
                        raise ValueError("Wait for the current queue to finish before changing the root folder.")
                chosen = QFileDialog.getExistingDirectory(self.window, "Choose download root folder")
                if chosen:
                    with self.state.lock:
                        self.state.root = Path(chosen)
                        web_app.ROOT_STORE.write_text(chosen, encoding="utf-8")
                result = {"root": str(self.state.root) if self.state.root else None}
            elif path == "choose-cookies" and method == "POST":
                chosen, _ = QFileDialog.getOpenFileName(
                    self.window, "Choose Netscape cookies file", "", "Text files (*.txt);;All files (*)"
                )
                result = {"path": chosen or None}
            elif path == "queue" and method == "POST":
                count = self.state.add(
                    data.get("platform", ""), data.get("folders", []),
                    int(data.get("limit", 10)), int(data.get("concurrency", 1)),
                    data.get("cookiefile", ""), data.get("cookies_text", ""), data.get("browser", ""),
                )
                result = {"queued": count}
            elif path == "stop" and method == "POST":
                self.state.stop()
                result = {"stopped": True}
            elif path == "copy-username" and method == "POST":
                name = data.get("name", "")
                if not web_app.valid_username(name):
                    raise ValueError("Invalid creator username.")
                QApplication.clipboard().setText(name)
                result = {"copied": True}
            else:
                raise ValueError("Unknown desktop action.")
            return json.dumps(result, ensure_ascii=False)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def create_window() -> tuple[QMainWindow, NativeState, QWebEngineView]:
    window = QMainWindow()
    window.setWindowTitle("Clipnest")
    window.resize(1440, 900)
    window.setMinimumSize(880, 620)
    view = QWebEngineView(window)
    page = DesktopPage(view)
    view.setPage(page)
    window.setCentralWidget(view)
    state = NativeState()
    bridge = DesktopBridge(state, window)
    channel = QWebChannel(page)
    channel.registerObject("clipnest", bridge)
    page.setWebChannel(channel)
    view.load(QUrl.fromLocalFile(str(WEB_DIR / "index.html")))
    window._clipnest_bridge = bridge
    window._clipnest_channel = channel
    return window, state, view


def main() -> int:
    downloader.prepare_runtime()
    app = QApplication(sys.argv)
    app.setApplicationName("Clipnest")
    window, state, _view = create_window()
    app.aboutToQuit.connect(state.stop)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
