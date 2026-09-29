"""Desktop video download queue for supported public URLs."""

from __future__ import annotations

import queue
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv", ".wmv", ".ts"}
ALLOWED_HOSTS = ("youtube.com", "youtu.be", "tiktok.com", "instagram.com")


def supported_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and any(
        host == domain or host.endswith("." + domain) for domain in ALLOWED_HOSTS
    )


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
    url: str
    folder: Path
    limit: int


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Video Downloader")
        self.geometry("1040x720")
        self.minsize(790, 560)
        self.root_folder: Path | None = None
        self.folder_paths: dict[str, Path] = {}
        self.events: queue.Queue[tuple] = queue.Queue()
        self.busy = False
        self.stop_requested = threading.Event()
        self.root_label = tk.StringVar(value="Choose a root folder to begin")
        self.limit_value = tk.StringVar(value="10")
        self.workers_value = tk.StringVar(value="2")
        self.summary = tk.StringVar(value="Ready")
        self._build_ui()
        self.after(100, self._process_events)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Video Downloader", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Queue YouTube, TikTok, and Instagram URLs into selected folders.").pack(anchor="w", pady=(0, 12))

        root_bar = ttk.Frame(outer)
        root_bar.pack(fill="x", pady=(0, 10))
        ttk.Button(root_bar, text="Choose root folder", command=self._choose_root).pack(side="left")
        ttk.Label(root_bar, textvariable=self.root_label).pack(side="left", padx=12)
        ttk.Button(root_bar, text="Rescan", command=self._scan_folders).pack(side="right")

        folders_frame = ttk.LabelFrame(outer, text="Subfolders — select one or more", padding=8)
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

        input_frame = ttk.LabelFrame(outer, text="Video or playlist URLs — one per line", padding=8)
        input_frame.pack(fill="x", pady=(12, 0))
        self.urls = tk.Text(input_frame, height=4, wrap="none")
        self.urls.pack(fill="x")

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=10)
        ttk.Label(options, text="Max videos per URL (0 = all):").pack(side="left")
        ttk.Entry(options, textvariable=self.limit_value, width=6).pack(side="left", padx=(6, 24))
        ttk.Label(options, text="Concurrent downloads:").pack(side="left")
        ttk.Entry(options, textvariable=self.workers_value, width=6).pack(side="left", padx=6)
        self.queue_button = ttk.Button(options, text="Add to queue", command=self._add_to_queue)
        self.queue_button.pack(side="right")
        self.stop_button = ttk.Button(options, text="Stop after current downloads", command=self._stop, state="disabled")
        self.stop_button.pack(side="right", padx=8)

        queue_frame = ttk.LabelFrame(outer, text="Download queue", padding=8)
        queue_frame.pack(fill="both", expand=True)
        self.jobs = ttk.Treeview(queue_frame, columns=("folder", "url", "progress", "status"), show="headings", height=8)
        for column, heading, width in (("folder", "Folder", 190), ("url", "URL", 410), ("progress", "Progress", 90), ("status", "Status", 230)):
            self.jobs.heading(column, text=heading)
            self.jobs.column(column, width=width, anchor="w")
        self.jobs.pack(side="left", fill="both", expand=True)
        job_scroll = ttk.Scrollbar(queue_frame, orient="vertical", command=self.jobs.yview)
        job_scroll.pack(side="right", fill="y")
        self.jobs.configure(yscrollcommand=job_scroll.set)
        ttk.Label(outer, textvariable=self.summary).pack(anchor="w", pady=(8, 0))

    def _choose_root(self) -> None:
        chosen = filedialog.askdirectory(title="Choose root folder")
        if chosen:
            self.root_folder = Path(chosen)
            self.root_label.set(str(self.root_folder))
            self._scan_folders()

    def _scan_folders(self) -> None:
        self.folders.delete(*self.folders.get_children())
        self.folder_paths.clear()
        if self.root_folder is None:
            return
        try:
            children = sorted((p for p in self.root_folder.iterdir() if p.is_dir()), key=lambda p: p.name.lower())
        except OSError as exc:
            messagebox.showerror("Folder error", str(exc))
            return
        for child in children:
            row_id = self.folders.insert("", "end", values=(child.name, video_count(child)))
            self.folder_paths[row_id] = child
        self.summary.set(f"Found {len(children)} subfolders. Select one or more to download into.")

    def _add_to_queue(self) -> None:
        if self.busy:
            return
        selected = self.folders.selection()
        urls = list(dict.fromkeys(line.strip() for line in self.urls.get("1.0", "end").splitlines() if line.strip()))
        if not selected or not urls:
            messagebox.showinfo("Choose folders and URLs", "Select at least one subfolder and enter at least one URL.")
            return
        invalid = [url for url in urls if not supported_url(url)]
        if invalid:
            messagebox.showerror("Unsupported URL", "Use http(s) links from YouTube, TikTok, or Instagram.\n\n" + invalid[0])
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
        tasks = []
        for folder_id in selected:
            folder = self.folder_paths[folder_id]
            for url in urls:
                row = self.jobs.insert("", "end", values=(folder.name, url, "0%", "Queued"))
                tasks.append(Job(row, url, folder, limit))
        self.busy = True
        self.stop_requested.clear()
        self.queue_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.summary.set(f"Queued {len(tasks)} downloads across {len(selected)} folders.")
        threading.Thread(target=self._run_batch, args=(tasks, workers), daemon=True).start()

    def _stop(self) -> None:
        self.stop_requested.set()
        self.stop_button.configure(state="disabled")
        self.summary.set("Stopping after active downloads finish…")

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
        try:
            import yt_dlp

            def progress(data: dict) -> None:
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
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": False,
                "windowsfilenames": True,
            }
            with yt_dlp.YoutubeDL(options) as downloader:
                result = downloader.download([job.url])
            status = "Done" if result == 0 else "Failed"
            self.events.put(("status", job.row_id, "100%" if result == 0 else "—", status))
            return status
        except Exception as exc:
            detail = str(exc).replace("\n", " ")[:180]
            self.events.put(("status", job.row_id, "—", "Failed: " + detail))
            return "Failed"

    def _process_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "status":
                    _, row, progress, status = event
                    if self.jobs.exists(row):
                        self.jobs.set(row, "progress", progress)
                        self.jobs.set(row, "status", status)
                elif event[0] == "batch_done":
                    results = event[1]
                    self.busy = False
                    self.queue_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.summary.set(f"Finished: {results.count('Done')} done, {results.count('Failed')} failed, {results.count('Stopped')} stopped.")
                    self._scan_folders()
                    self.summary.set(f"Finished: {results.count('Done')} done, {results.count('Failed')} failed, {results.count('Stopped')} stopped.")
        except queue.Empty:
            pass
        self.after(100, self._process_events)


if __name__ == "__main__":
    DownloaderApp().mainloop()
