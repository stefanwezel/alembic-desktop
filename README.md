# Alembic

A desktop application for sorting and curating image collections. Select a folder of images, sweep through them to keep or discard, then download your sorted set.

## Install

Download the latest release from the [Releases](https://github.com/stefanwezel/alembic-desktop/releases) page.

**Linux (AppImage):**
```bash
chmod +x Alembic_*.AppImage
./Alembic_*.AppImage
```

**Windows:** run `Alembic_*_x64-setup.exe` to install for yourself, or `Alembic_*_x64_en-US.msi` to
install for everyone on the machine (that one asks for administrator rights). The installers are not
code signed, so SmartScreen greets the download with "Windows protected your PC" — open **More info**
and choose **Run anyway**. Installing needs an internet connection the first time on a machine
without WebView2 (Windows 11 and up-to-date Windows 10 already have it).

## Prerequisites

- **Rust** (stable toolchain) — [rustup.rs](https://rustup.rs)
- **Python 3.12**
- **System libraries** (Ubuntu/Debian):
  ```bash
  sudo apt-get install -y pkg-config libglib2.0-dev libgtk-3-dev libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev libsoup-3.0-dev libayatana-appindicator3-dev librsvg2-dev libssl-dev patchelf libturbojpeg0-dev
  ```
- **On Windows**, instead of those libraries:
  - Visual Studio Build Tools with the "Desktop development with C++" workload, for the linker Rust uses
  - [libjpeg-turbo](https://github.com/libjpeg-turbo/libjpeg-turbo/releases) — the `vc64` installer,
    installed into `C:\libjpeg-turbo64`, which is where `alembic-api.spec` and `app/turbojpeg.py` look
  - Git Bash, to run the `scripts/*.sh` below

## Build from source

```bash
./scripts/build.sh
```

This builds the Python sidecar and produces a distributable package via `cargo tauri build`.

## Development

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r app/requirements.txt pyinstaller==6.19.0

# Build the Python sidecar (required before first run and after any Python changes)
./scripts/rebuild-sidecar.sh

# Start in dev mode (hot-reloads frontend; Python changes need sidecar rebuild)
cargo tauri dev

# Run tests
pytest tests/unit/
```

## How it works

When you load a folder, each image is processed into three cached sizes (thumbnail, preview, display) and a **384-dimensional embedding** is generated locally using an EfficientNet B0 model via ONNX Runtime. During sweeping, the app uses L2 distance between embeddings to always show you the most visually similar unreviewed image next to your current one.

**Supported formats:** JPG, PNG, TIFF, and RAW files (DNG, CR2, NEF, ARW). RAW formats are automatically converted to JPG during processing.

## Keyboard shortcuts (sweep view)

| Left image | Right image | Action |
|---|---|---|
| D | K | Keep |
| S | L | Continue from |
| F | J | Drop |

- **R** — Reset zoom on both images
- **Mouse wheel** — Zoom in/out
- **Click + drag** — Pan

## Usage

1. Select a folder containing images
2. Sweep through images — keep or discard each one
3. Download your sorted set

## Data storage

All application data lives in `~/.alembic/` (`C:\Users\<you>\.alembic` on Windows) — this includes the
SQLite database (`alembic.db`) and the image cache.
