# Clipnest user guide

## Install

Open the [latest GitHub release](https://github.com/DaroDaro009/clipnest/releases/latest) and download `Clipnest_0.2.0_x64-setup.exe`. Run it, then open Clipnest from the Start menu. The optional `Clipnest.exe` runs without installation. Neither requires Python, Node.js, FFmpeg, WebView2, or a terminal on the new PC.

## Prepare creator folders

Make one root folder with subfolders named after the creators:

```text
Videos/
  ethan.hunt398/
  khunkaw.ri/
```

Choose `Videos` in Clipnest. Each subfolder name is a creator username for the selected platform. Do not put full URLs in folder names. Existing videos stay in place; new videos go into the matching subfolder.

## Download

1. Choose the root folder and TikTok, YouTube Shorts, or Instagram.
2. Review the video counts. Folders with zero videos appear first.
3. Select folders, use **Select all**, or use **Select under video limit**. **Copy username** copies the selected folder name.
4. Set **Videos per creator** (`0` means all available) and **Concurrent downloads** (1–8). Start with 1 when testing a new PC.
5. Click **Download selected**. The queue shows the current video title, progress, and status. Select a queue row to read its full status or error.

**Stop downloads** cancels active work at its next progress update and marks waiting jobs Stopped. A partial transfer may resume on the next attempt. **Rescan** refreshes the folder counts. Completed files use video titles, with `(2)`, `(3)`, and so on for repeated titles. The archive file in each creator folder prevents downloading the same video ID again.

YouTube uses each creator's **Shorts** tab only. A **Partial** result means at least one video was saved but another failed.

## Cookies

In **Cookie settings**, choose Chrome, Edge, or Firefox, select a Netscape `cookies.txt` file, or paste that file's contents. Settings are saved automatically for each platform and encrypted for your Windows account. **Clear** removes the current platform's saved cookie setting. Each person using Clipnest on another PC should enter their own cookies if needed; do not share account cookies or `%LOCALAPPDATA%\Clipnest`.

## If a download fails

- **TikTok profile cannot be read:** Confirm the creator folder name and try fresh cookies. Clipnest also checks TikTok's public creator embed when the standard profile lookup fails.
- **YouTube page needs to be reloaded:** Clipnest retries public Shorts without saved cookies. If the retry fails, check that the creator and Shorts page open in the browser on that PC.
- **Requested format is not available:** Use the new setup, which bundles FFmpeg. Some individual videos may still have restricted formats.
- **`getaddrinfo failed` or DNS:** Windows could not resolve a video server. Check the PC's internet, DNS, VPN, and firewall. The app cannot fix a failed network lookup.
- **HTTP 403:** The platform refused that video request. Try one creator at a time and refresh that platform's cookies. Some videos remain unavailable.

The selected queue row shows the actual error. Retry after changing the relevant setting. Download content only when you have permission and follow the platform's rules.
