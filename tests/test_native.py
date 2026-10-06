import queue
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from downloader import DownloaderApp, Job, profile_url


class NativeTests(unittest.TestCase):
    def test_creator_folder_maps_to_profile(self):
        self.assertEqual(profile_url("youtube", "AnimalOope"), "https://www.youtube.com/@AnimalOope/shorts")
        self.assertEqual(profile_url("tiktok", "ethan.hunt398"), "https://www.tiktok.com/@ethan.hunt398")
        self.assertEqual(profile_url("instagram", "creator"), "https://www.instagram.com/creator/")

    def test_native_download_uses_shorts_and_can_stop(self):
        events = queue.Queue()
        stopped = threading.Event()
        harness = types.SimpleNamespace(events=events, stop_requested=stopped)
        options_seen = []

        class FakeDownloader:
            def __init__(self, options):
                self.options = options
                options_seen.append(options)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def add_post_processor(self, *_args, **_kwargs):
                pass

            def download(self, urls):
                self.options["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10, "info_dict": {"title": "A Short"}})
                stopped.set()
                self.options["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 6, "total_bytes": 10})
                return 0

        fake_yt_dlp = types.SimpleNamespace(
            YoutubeDL=FakeDownloader,
            postprocessor=types.SimpleNamespace(PostProcessor=object),
            utils=types.SimpleNamespace(DownloadError=RuntimeError),
        )
        job = Job("row", "youtube", profile_url("youtube", "creator"), Path("creator"), 10, "", "", "")
        with patch.dict(sys.modules, {"yt_dlp": fake_yt_dlp}), patch("downloader.shutil.which", return_value="ffmpeg.exe"):
            result = DownloaderApp._run_job(harness, job)
        self.assertEqual(result, "Stopped")
        self.assertEqual(options_seen[0]["js_runtimes"], {"node": {}})
        self.assertEqual(options_seen[0]["playlistend"], 10)
        self.assertEqual(options_seen[0]["format"], "bestvideo*+bestaudio/best")
        self.assertEqual(options_seen[0]["merge_output_format"], "mp4")
        self.assertTrue(any(event[0] == "title" and event[2] == "A Short" for event in list(events.queue)))

    def test_download_error_is_failed_without_user_stop(self):
        events = queue.Queue()
        harness = types.SimpleNamespace(events=events, stop_requested=threading.Event())

        class FakeDownloader:
            def __init__(self, _options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def add_post_processor(self, *_args, **_kwargs):
                pass

            def download(self, _urls):
                raise RuntimeError("HTTP Error 403: Forbidden")

        fake_yt_dlp = types.SimpleNamespace(
            YoutubeDL=FakeDownloader,
            postprocessor=types.SimpleNamespace(PostProcessor=object),
            utils=types.SimpleNamespace(DownloadError=RuntimeError),
        )
        job = Job("row", "youtube", profile_url("youtube", "creator"), Path("creator"), 1, "", "", "")
        with patch.dict(sys.modules, {"yt_dlp": fake_yt_dlp}):
            result = DownloaderApp._run_job(harness, job)
        self.assertEqual(result, "Failed")
        self.assertIn(("status", "row", "—", "Failed"), list(events.queue))
        self.assertTrue(any(event[0] == "detail" and "403" in event[2] for event in list(events.queue)))


if __name__ == "__main__":
    unittest.main()
