# Build Clipnest for Windows

## Requirements

- 64-bit Windows with Microsoft C++ build tools and WebView2
- Node.js and npm
- Rust with the `x86_64-pc-windows-msvc` target
- Python 3.12 or newer and pip

From the project root, run:

```powershell
python -m pip install -r requirements.txt pyinstaller
npm ci
python -m unittest discover -s tests -v
python build_sidecar.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare_windows_runtime.ps1
npm run tauri build
```

The Windows setup file is written to `src-tauri/target/release/bundle/nsis/`. `build_sidecar.py` first packages `web_app.py` as a windowless executable inside the installer. The runtime preparation script copies Node.js from the installed build toolchain into the bundle, along with its license, so YouTube's JavaScript challenges work without a separate installation. The installed Tauri app starts the service on a private localhost port and stops it when the window closes.

Never commit `.clipnest-cookies.dat`, `.clipnest-root.txt`, `.clipnest-tiktok-ids.json`, downloaded videos, `.vendor/`, `.build-tools/`, or the generated installer. The setup file belongs on a GitHub Release, not in the source tree.

## GitHub release workflow

The workflow in `.github/workflows/windows-release.yml` can be started from the repository's **Actions** tab. It installs dependencies on a Windows runner, runs the tests, builds the Python sidecar and Tauri installer, and uploads the installer to a release named for the version in `src-tauri/tauri.conf.json`.

For a new release, update the version in `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, and `package.json`, commit the changes, then run the workflow. `package-lock.json` and `src-tauri/Cargo.lock` should be updated with the same version. Keep user cookies and selected folders out of the release.
