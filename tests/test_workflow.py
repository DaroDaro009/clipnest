import threading
import tempfile
import sys
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import web_app


class WorkflowTests(unittest.TestCase):
    def test_youtube_profile_uses_shorts_tab(self):
        self.assertEqual(
            web_app.profile_url("youtube", "creator_name"),
            "https://www.youtube.com/@creator_name/shorts",
        )

    def test_stop_interrupts_active_download_and_clears_pending(self):
        state = web_app.State()
        state.root = web_app.HERE
        active = web_app.Download(str(uuid.uuid4()), "youtube", "creator_name", "https://www.youtube.com/@creator_name/shorts")
        waiting = web_app.Download(str(uuid.uuid4()), "youtube", "creator_name", active.url)
        state.jobs.extend((active, waiting))
        state.cancel_events[active.id] = threading.Event()
        state.cancel_events[waiting.id] = threading.Event()
        state.active = 1
        active.status = "Downloading"
        state.pending.put((waiting, 1, "", "", ""))

        class FakeDownloader:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def add_post_processor(self, *_args, **_kwargs):
                pass

            def download(self, _urls):
                progress = self.options["progress_hooks"][0]
                progress({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 10})
                state.stop()
                try:
                    progress({"status": "downloading", "downloaded_bytes": 2, "total_bytes": 10})
                except Exception:
                    return 0
                return 0

        fake_yt_dlp = types.SimpleNamespace(
            YoutubeDL=FakeDownloader,
            postprocessor=types.SimpleNamespace(PostProcessor=object),
            utils=types.SimpleNamespace(DownloadError=RuntimeError),
        )
        with patch.dict(sys.modules, {"yt_dlp": fake_yt_dlp}):
            state._download(active, 1, "", "", "")

        self.assertEqual(active.status, "Stopped")
        self.assertEqual(waiting.status, "Stopped")
        self.assertEqual(state.active, 0)
        self.assertTrue(state.pending.empty())
        state.executor.shutdown(wait=True)

    def test_youtube_reload_error_retries_public_shorts_without_cookies(self):
        state = web_app.State()
        state.root = web_app.HERE
        job = web_app.Download(str(uuid.uuid4()), "youtube", "creator_name", "https://www.youtube.com/@creator_name/shorts")
        state.jobs.append(job)
        state.cancel_events[job.id] = threading.Event()
        state.active = 1
        attempts = []

        class FakeDownloader:
            def __init__(self, options):
                attempts.append(options)
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def add_post_processor(self, *_args, **_kwargs):
                pass

            def download(self, _urls):
                if "cookiesfrombrowser" in self.options:
                    raise RuntimeError("ERROR: [youtube] The page needs to be reloaded.")
                return 0

        fake_yt_dlp = types.SimpleNamespace(
            YoutubeDL=FakeDownloader,
            postprocessor=types.SimpleNamespace(PostProcessor=object),
            utils=types.SimpleNamespace(DownloadError=RuntimeError),
        )
        with patch.dict(sys.modules, {"yt_dlp": fake_yt_dlp}), patch("web_app.shutil.which", return_value="ffmpeg.exe"):
            state._download(job, 1, "", "", "chrome")

        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["js_runtimes"], {"node": {}})
        self.assertEqual(attempts[0]["format"], "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo*+bestaudio/best")
        self.assertEqual(attempts[0]["merge_output_format"], "mp4")
        self.assertEqual(attempts[0]["source_address"], "0.0.0.0")
        self.assertEqual(attempts[0]["ignoreerrors"], "only_download")
        self.assertNotIn("cookiesfrombrowser", attempts[1])
        self.assertEqual(job.status, "Done")
        state.executor.shutdown(wait=True)

    def test_youtube_continues_after_one_failed_short(self):
        with tempfile.TemporaryDirectory(dir=web_app.HERE) as temp:
            state = web_app.State()
            state.root = Path(temp)
            folder = state.root / "creator_name"
            folder.mkdir()
            job = web_app.Download(str(uuid.uuid4()), "youtube", "creator_name", "https://www.youtube.com/@creator_name/shorts")
            state.jobs.append(job)
            state.cancel_events[job.id] = threading.Event()
            state.active = 1

            class FakeDownloader:
                def __init__(self, options):
                    self.options = options

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    return False

                def add_post_processor(self, processor, **_kwargs):
                    self.processor = processor

                def download(self, _urls):
                    video = folder / "working [abc123].mp4"
                    video.write_bytes(b"video")
                    self.processor.run({"filepath": str(video), "id": "abc123"})
                    self.options["logger"].error("ERROR: unable to download video data: HTTP Error 403: Forbidden")
                    return 1

            fake_yt_dlp = types.SimpleNamespace(
                YoutubeDL=FakeDownloader,
                postprocessor=types.SimpleNamespace(PostProcessor=object),
                utils=types.SimpleNamespace(DownloadError=RuntimeError),
            )
            with patch.dict(sys.modules, {"yt_dlp": fake_yt_dlp}):
                state._download(job, 2, "", "", "")

            self.assertEqual(job.status, "Partial")
            self.assertIn("Saved 1 video", job.detail)
            self.assertIn("403", job.detail)
            self.assertTrue((folder / "working.mp4").is_file())
            state.executor.shutdown(wait=True)

    def test_dns_error_identifies_this_pc(self):
        message = web_app.explain_download_error("getaddrinfo failed ([Errno 11001])", "youtube")
        self.assertIn("This PC", message)
        self.assertIn("DNS", message)


if __name__ == "__main__":
    unittest.main()
