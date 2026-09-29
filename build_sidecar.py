"""Build Clipnest's hidden Python downloader for the Tauri bundle."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".build-tools"))

import PyInstaller.__main__


PyInstaller.__main__.run([
    str(ROOT / "web_app.py"),
    "--name", "clipnest-server",
    "--onefile",
    "--windowed",
    "--noupx",
    "--noconfirm",
    "--clean",
    "--paths", str(ROOT / ".vendor"),
    "--add-data", f"{ROOT / 'web'};web",
    "--collect-all", "yt_dlp",
    "--collect-all", "curl_cffi",
    "--hidden-import", "chardet",
    "--distpath", str(ROOT / "src-tauri" / "binaries"),
    "--workpath", str(ROOT / "build" / "pyinstaller"),
    "--specpath", str(ROOT / "build"),
])
