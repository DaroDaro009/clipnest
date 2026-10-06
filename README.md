# Clipnest

Clipnest is a Python desktop app for downloading public TikTok, YouTube Shorts, and Instagram creator videos into existing username folders. It shows the original Clipnest web interface inside its own desktop window and uses `downloader.py` with yt-dlp for transfers. The interface talks directly to Python inside the app; no browser tab, local web server, Tauri, or terminal is needed.

## Windows download

The [latest release](https://github.com/DaroDaro009/clipnest/releases/latest) includes a Windows setup EXE and a portable ZIP. The app bundles yt-dlp, Node.js, and FFmpeg, so another PC does not need Python installed. See the [user guide](docs/USER_GUIDE.md).

## Creator folder workflow

1. Make a root folder with one subfolder per creator username. For example, `Videos/ethan.hunt398/` maps to `https://www.tiktok.com/@ethan.hunt398` when TikTok is selected.
2. Choose the root folder and platform. YouTube maps the folder name to the creator's Shorts tab.
3. Select folders. The list shows existing video counts and sorts folders with fewer videos first. Use **Select all**, **Select under video limit**, or **Copy username**.
4. Set the per-creator limit and concurrency, then click **Download selected**. The queue shows the current video title, progress, result, and full error detail. **Stop downloads** interrupts active jobs and clears waiting work.
5. Videos are saved in their creator folders using their titles. Repeated titles receive `(2)`, `(3)`, and so on. An archive file records downloaded IDs to avoid repeats.

Cookies can be read from a browser, selected from a `cookies.txt` file, or pasted into the app. Pasted settings are saved with Windows account encryption. Cookies and downloaded videos are never included in a release.

Run from source with `python desktop.py` after installing `requirements.txt`. The [build guide](docs/BUILDING.md) explains Windows packaging. The interface lives in `web/`, the desktop bridge in `desktop.py`, and the Python download engine in `downloader.py`. The Tauri wrapper remains in the repository as reference; the release workflow builds the Python desktop app.

Download content only when you have permission and follow the platform's rules. Individual profiles and videos can still fail when a platform blocks access or the PC cannot reach its video servers.
