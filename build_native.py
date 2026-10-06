"""Build the native Clipnest Windows executable with PyInstaller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BINARIES = ROOT / "src-tauri" / "binaries"


def main() -> None:
    required = ("node.exe", "node-LICENSE", "ffmpeg.exe", "ffprobe.exe", "ffmpeg-LICENSE.txt")
    missing = [name for name in required if not (BINARIES / name).is_file()]
    if missing:
        raise SystemExit("Missing bundled runtime files: " + ", ".join(missing))
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", "Clipnest",
        "--icon", str(ROOT / "src-tauri" / "icons" / "icon.ico"),
        "--collect-all", "yt_dlp", "--collect-all", "curl_cffi",
        "--hidden-import", "chardet", "--hidden-import", "tkinter",
    ]
    for name in required:
        command.extend(("--add-binary", f"{BINARIES / name};binaries"))
    command.append(str(ROOT / "downloader.py"))
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
