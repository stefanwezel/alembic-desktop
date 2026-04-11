# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Alembic Desktop is a Tauri 2 desktop app for sorting/curating image collections. Users select a folder of images, sweep through them side-by-side (keep or discard), then download their sorted set. It uses image embeddings for similarity-based navigation.

## Architecture

Three-layer sidecar architecture:

- **Tauri/Rust shell** (`src-tauri/src/lib.rs`): Spawns the Python sidecar, polls its health endpoint, shows the window once ready, kills sidecar on shutdown.
- **Python Flask API** (`app/app.py`, port 3001): SQLAlchemy + SQLite (`~/.alembic/alembic.db`), image processing (OpenCV, rawpy, Pillow, TurboJPEG), 384-dim embedding vectors for similarity search. Embeddings are generated locally using an EfficientNet B0 ONNX model (16MB), producing 384-dim L2-normalized vectors for similarity search. No PyTorch dependency; post-processing uses numpy/cv2 only. Single-user desktop app (hardcoded user "desktop@localhost").
- **Vanilla JS frontend** (`frontend/`): No framework. Direct DOM manipulation with global state (`currentSessionId`, `currentIdLeft`, `currentIdRight`). Views toggled by showing/hiding `view-*` sections.

In dev mode, Tauri runs `python3 -m http.server 8080` to serve the frontend (hot-reload on file save), while the sidecar API runs on port 3001. The frontend communicates with the API via `fetch()` calls to `http://localhost:3001`.

Images go through progressive loading: thumbnail → preview → display. RAW formats (DNG, CR2, NEF, ARW) are converted to JPG via rawpy. Media cache lives at `~/.alembic/cache/`.

### Key domain patterns

- **Image status lifecycle**: `unreviewed` → `reviewed_keep` or `reviewed_discard`. The decision view shows two images; the user keeps, drops, or "continues from" one.
- **Endofline sentinel**: When no unreviewed images remain, `get_nearest_neighbor` returns a synthetic `Embedding` with all paths set to `"endofline"`. Frontend and backend both check for this to trigger session completion.
- **Schema versioning**: `AppMetadata` table stores `schema_version`. When `CURRENT_SCHEMA_VERSION` (in `app.py`) changes, all sessions and embeddings are wiped on startup to avoid incompatible data.

## Development Commands

```bash
# Prerequisites: Rust (via rustup) and Python 3.12+
# If cargo is not in PATH, run: source ~/.cargo/env

# Linux system dependencies (Ubuntu/Debian)
sudo apt-get install -y pkg-config libglib2.0-dev libgtk-3-dev libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev libsoup-3.0-dev libayatana-appindicator3-dev librsvg2-dev libssl-dev patchelf libturbojpeg0-dev

# Setup Python environment
python3 -m venv .venv && source .venv/bin/activate && pip install -r app/requirements.txt pyinstaller

# Build/rebuild the Python sidecar (required before first run and after any Python changes)
./scripts/rebuild-sidecar.sh

# Run in dev mode (hot-reload for frontend only; Python changes need sidecar rebuild)
cargo tauri dev

# Build production bundles (Linux .deb/.AppImage, macOS .dmg/.app, Windows .msi/.exe)
./scripts/build.sh

# Run Python unit tests
pytest tests/unit/

# Run a single test
pytest tests/unit/test_utils.py::test_load_jpg

# Format Python code
black --line-length 120 app/

# Format Rust code
cargo fmt -p alembic-desktop-lib
```

## Key Configuration

- `pyproject.toml`: Black formatter, 120-char line length
- `tauri.conf.json`: Window config (1400x900), CSP allowing localhost:3001, frontend served from `../frontend`
- `alembic-api.spec`: PyInstaller spec with platform-specific TurboJPEG bundling and hidden imports
- `LOG_LEVEL` env var controls Python logging level (default: ERROR)

The sidecar binary must be named `alembic-api-{target-triple}` (e.g. `alembic-api-x86_64-unknown-linux-gnu`) under `src-tauri/binaries/`. The `rebuild-sidecar.sh` script handles this automatically.

## Keyboard Shortcuts (Decision View)

- Left image: D (like), S (continue from), F (drop)
- Right image: K (like), L (continue from), J (drop)
- R: Reset zoom on both images
