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
        sys.executable, "-m", "PyInstaller", "--noconfirm",
        "--onedir", "--windowed", "--name", "Clipnest",
        "--icon", str(ROOT / "src-tauri" / "icons" / "icon.ico"),
        "--runtime-hook", str(ROOT / "qt_runtime_hook.py"),
        "--collect-all", "yt_dlp", "--collect-all", "curl_cffi",
        "--hidden-import", "chardet", "--hidden-import", "tkinter",
        "--add-data", f"{ROOT / 'web'};web",
    ]
    for name in required:
        command.extend(("--add-binary", f"{BINARIES / name};binaries"))
    command.append(str(ROOT / "desktop.py"))
    subprocess.run(command, cwd=ROOT, check=True)

    # PyInstaller can pick up ICU from unrelated software on the build PC.
    # Qt's Windows wheel uses the Windows ICU library; an unrelated copy can
    # make the frozen application fail before its first window opens.
    internal = ROOT / "dist" / "Clipnest" / "_internal"
    (internal / "icuuc.dll").unlink(missing_ok=True)
    for data_library in internal.glob("icudt*.dll"):
        data_library.unlink()


if __name__ == "__main__":
    main()
