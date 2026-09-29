"""Build Clipnest's hidden Python downloader for the Tauri bundle."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".build-tools"))
LOCAL_WHEELS = ROOT / ".build-tools" / "ci-deps"
if LOCAL_WHEELS.is_dir():
    sys.path.insert(0, str(LOCAL_WHEELS))

import PyInstaller.__main__


args = [
    str(ROOT / "web_app.py"),
    "--name", "clipnest-server",
    "--onefile",
    "--windowed",
    "--noupx",
    "--noconfirm",
    "--clean",
    "--add-data", f"{ROOT / 'web'};web",
    "--collect-all", "yt_dlp",
    "--collect-all", "curl_cffi",
    "--hidden-import", "chardet",
    "--distpath", str(ROOT / "src-tauri" / "binaries"),
    "--workpath", str(ROOT / "build" / "pyinstaller"),
    "--specpath", str(ROOT / "build"),
]
if LOCAL_WHEELS.is_dir():
    args.extend(["--paths", str(LOCAL_WHEELS)])
if (ROOT / ".vendor").is_dir():
    args.extend(["--paths", str(ROOT / ".vendor")])
PyInstaller.__main__.run(args)
