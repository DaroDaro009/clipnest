# Clipnest user guide

## Install

1. Open the [latest release](https://github.com/DaroDaro009/clipnest/releases/latest).
2. Under **Assets**, download `Clipnest_..._x64-setup.exe`. The source code ZIP is for developers and is not the installer.
3. Run the setup file and open Clipnest from the Start menu. Clipnest opens its own window. No terminal needs to stay open.

Clipnest is built for 64-bit Windows. The installer may need an internet connection to obtain Microsoft's WebView2 runtime if it is missing. This release is not code signed, so Windows may show a publisher warning; verify that you obtained the file from this repository's release page before running it.

To update, run the setup file from a newer release. Your chosen root folder and saved cookie settings are stored separately under `%LOCALAPPDATA%\Clipnest` and are not packaged into the installer.

## Prepare creator folders

Create a root folder containing one subfolder per creator username. Examples:

```text
Videos/
  ethan.hunt398/
  khunkaw.ri/
```

Choose **Videos** as the root folder. Clipnest treats each subfolder name as a creator username for the selected platform. Do not put profile URLs in folder names. Existing videos stay in place; new videos go into the matching subfolder.

## Download

1. Select the platform: TikTok, YouTube, or Instagram.
2. Click **Choose folder** and select your root folder.
3. Review the video counts. Folders with zero videos appear first.
4. Select folders individually, use **Select all**, or choose folders under the current video count threshold. Use **Copy** beside a folder to copy its username.
5. Set **Videos per creator**. A value of `0` asks for every video the platform makes available. Set concurrency from 1 to 8.
6. Click **Download selected creators**. Watch the queue for progress, titles, and errors.

**Stop downloads** clears waiting jobs and interrupts active transfers at their next progress update. A partial file may resume when you try again. **Rescan** refreshes the folder counts. An archive file inside each creator folder helps prevent duplicate downloads. Files use their video titles; repeated titles are numbered.

For YouTube, a **Partial** result means some Shorts were saved and others failed. Clipnest continues to the next Short after an individual download error. Start with concurrency **1** if you see connection failures or HTTP 403 errors.

YouTube downloads come from each creator's **Shorts** tab. Regular YouTube videos are excluded.

## Cookies

Open **Cookie settings** if a platform needs your logged-in session. You can choose Chrome, Edge, or Firefox, select a Netscape-format `cookies.txt` file, or paste that file's contents. Clipnest saves these settings automatically and encrypts them for your Windows user account. Use **Clear saved cookies** to remove one platform's saved setting.

Cookie settings stay on your computer. Do not share your cookies, account session, or the contents of `%LOCALAPPDATA%\Clipnest` with other users. Each person should enter their own cookies if needed.

## If a download fails

- **TikTok creator ID or security challenge:** Open the creator profile in your browser and refresh the saved TikTok cookies. Clipnest also tries TikTok's public creator embed, but TikTok may block both routes.
- **No public videos:** The creator page may be empty, private, or unavailable from your location. A public embed can show fewer posts than the full profile.
- **YouTube "page needs to be reloaded":** Clipnest retries public Shorts without cookies. If the retry fails, confirm the creator username and that the Short is accessible in your browser. Videos requiring a logged-in account may still fail.
- **Other YouTube or Instagram error:** Confirm the creator username and that the posts are accessible in your browser. Some videos require a logged-in account.
- **Merging or format error:** Install the latest Clipnest setup. It includes FFmpeg to combine YouTube's separate video and audio streams, and Node.js for YouTube's JavaScript challenges.
- **YouTube DNS error (`getaddrinfo failed`):** Windows could not find YouTube's video server. Check this PC's network, VPN, and DNS settings. Clipnest uses IPv4 for YouTube, but cannot repair a broken DNS connection.
- **YouTube HTTP 403:** YouTube refused a video request. Try one creator at a time and check the YouTube cookie setting on this PC. Some videos may remain unavailable.

The queue shows the error for each creator. You can retry a failed folder after changing its settings.
