# Clipnest

Clipnest is a Windows desktop app that saves videos from selected TikTok, YouTube Shorts, and Instagram creator folders. It shows each folder's video count, puts folders with zero videos first, and displays download progress. The desktop app uses Tauri and starts its local downloader without a terminal window.

## Download for Windows

Get **Clipnest Setup.exe** from the [latest GitHub release](https://github.com/DaroDaro009/clipnest/releases/latest). Run the setup file, then open Clipnest from the Start menu. You do not need Python, Node.js, or Rust to use the installed app.

See the [user guide](docs/USER_GUIDE.md) for folder setup, cookies, limits, and troubleshooting. Developers can use the [build guide](docs/BUILDING.md).

## How it works

1. Make a root folder with one subfolder per creator. For example, `Videos/ethan.hunt398/` is the TikTok creator `https://www.tiktok.com/@ethan.hunt398`.
2. Choose that root folder in Clipnest and select TikTok, YouTube, or Instagram.
3. Select creator folders, set the number of videos per creator and concurrent downloads, then start the queue.
4. Videos are saved into their existing creator folders using video titles. Repeated titles get `(2)`, `(3)`, and so on. The app remembers downloaded video IDs to avoid duplicates.

YouTube uses creator **Shorts** pages only. TikTok sometimes blocks its main profile page; Clipnest then tries the public creator embed, which may expose only recent public posts. Some profiles or videos cannot be accessed even with cookies. Instagram profile extraction can also fail when its site changes.

Download only content you have permission to save and follow each platform's rules.

## Source and releases

The interface is in `web/`, the Python downloader is `web_app.py`, and the Tauri desktop wrapper is in `src-tauri/`. A Windows GitHub Actions workflow can build the setup file for future releases. Local cookies, selected folders, downloaded videos, and build tools are excluded from the repository.
