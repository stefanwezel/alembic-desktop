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
pip install -r app/requirements.txt

# Start in dev mode (hot-reloads frontend + sidecar)
cargo tauri dev
```

## Usage

1. Select a folder containing images
2. Sweep through images — keep or discard each one
3. Download your sorted set
