# Build Clipnest for Windows

The release is a Python desktop application packaged by PyInstaller. PySide6 displays the existing interface from `web/` inside the app, and Qt WebChannel connects its controls directly to Python. Downloads use `downloader.py`. It does not use Tauri, a local HTTP server, or the system WebView2 runtime.

## Local build

Requirements: 64-bit Windows, Python 3.12, Node.js 22 or newer, and NSIS for the setup installer. From the project root:

```powershell
python -m pip install -r requirements.txt pyinstaller
python -m unittest discover -s tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare_windows_runtime.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare_ffmpeg.ps1
python build_native.py
Push-Location installer
makensis /DAPP_VERSION=0.2.1 clipnest.nsi
Pop-Location
```

The portable app is the `dist/Clipnest/` folder; keep `Clipnest.exe` and `_internal/` together. The setup file is `dist/Clipnest_0.2.1_x64-setup.exe`. Both contain the same interface, Python downloader, yt-dlp, Node.js, FFmpeg, and Qt desktop runtime. PyInstaller uses `--windowed`, so the user sees no terminal window. The installer adds a Start menu shortcut and an uninstaller.

The runtime preparation scripts copy Node.js from the build PC and verify a pinned LGPL FFmpeg archive before packaging it. FFmpeg's license is bundled. The [FFmpeg build scripts](https://github.com/BtbN/FFmpeg-Builds) and [source](https://github.com/FFmpeg/FFmpeg/tree/n8.1.3) are available online.

## GitHub release

The **Native Windows release** workflow in `.github/workflows/windows-release.yml` builds and publishes the setup EXE and portable ZIP from a Windows runner. Update the version in the workflow and NSIS script for the next release, commit, and run the workflow from the Actions tab. Check its test and build results before sharing the release URL.

Do not commit cookie stores, selected folder paths, downloaded videos, `.vendor/`, `.build-tools/`, `src-tauri/binaries/`, or `dist/`. The app stores each user's settings under `%LOCALAPPDATA%\Clipnest` on the installed PC.
