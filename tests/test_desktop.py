import threading
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import web_app
from desktop import NativeState


class DesktopStateTests(unittest.TestCase):
    def test_queue_updates_match_python_download_engine(self):
        with TemporaryDirectory(dir=web_app.HERE) as temp:
            state = NativeState()
            state.root = Path(temp)
            folder = state.root / "creator"
            folder.mkdir()
            job = web_app.Download(str(uuid.uuid4()), "youtube", "creator", "https://www.youtube.com/@creator/shorts")
            state.jobs.append(job)
            state.cancel_events[job.id] = threading.Event()
            state.active = 1

            def fake_download(adapter, work):
                self.assertEqual(work.url, job.url)
                self.assertEqual(work.folder, folder)
                adapter.events.put(("title", job.id, "A Short"))
                adapter.events.put(("status", job.id, "62%", "Downloading"))
                adapter.events.put(("detail", job.id, "Saved a video"))
                adapter.events.put(("status", job.id, "100%", "Done"))
                return "Done"

            with patch("desktop.downloader.DownloaderApp._run_job", fake_download):
                state._download(job, 10, "", "", "")

            self.assertEqual(job.title, "A Short")
            self.assertEqual(job.progress, 100)
            self.assertEqual(job.status, "Done")
            self.assertEqual(job.detail, "Saved a video")
            self.assertEqual(state.active, 0)
            state.executor.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
