# Alembic

A desktop application for sorting and curating image collections. Select a folder of images, sweep through them to keep or discard, then download your sorted set.

## Prerequisites

- **Rust** (stable toolchain) — [rustup.rs](https://rustup.rs)
- **Python 3.12**
- **System libraries** (Ubuntu/Debian):
  ```bash
  sudo apt-get install -y pkg-config libglib2.0-dev libgtk-3-dev libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev libsoup-3.0-dev libayatana-appindicator3-dev librsvg2-dev libssl-dev patchelf libturbojpeg0-dev
  ```

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
pip install -r app/requirements.txt pyinstaller

# Build the Python sidecar (required before first run and after any Python changes)
./scripts/rebuild-sidecar.sh

# Start in dev mode (hot-reloads frontend; Python changes need sidecar rebuild)
cargo tauri dev
```

## How it works

When you load a folder, each image is processed into three cached sizes (thumbnail, preview, display) and a **384-dimensional embedding** is generated locally. The embedding is created by resizing the image to 8x16 pixels (8x16x3 = 384 values), flattening, and L2-normalizing. During sweeping, the app uses L2 distance between embeddings to always show you the most visually similar unreviewed image next to your current one.

## Usage

1. Select a folder containing images
2. Sweep through images — keep or discard each one
3. Download your sorted set
