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
- **End of a sweep**: `get_nearest_neighbor` returns `None` once nothing unreviewed is left. The next-pair payload then carries `null` for the side that has no image; the frontend renders the end-of-line placeholder there and wires up no buttons or shortcuts for it, so the last remaining image can still be reviewed. Reviewing that image returns `{"status": "completed"}`.
- **Legacy endofline rows**: Sessions created before that change contain a synthetic `Embedding` with every path set to `"endofline"` (the `ENDOFLINE` constant in `app.py`). Nothing creates them any more; they are filtered out of every query and can never be reviewed or exported.
- **Export**: `/download` takes a `destination` (a path the user picked with the native save dialog) and writes
  the zip straight there. The GET form that streams the archive back over HTTP is only for the frontend opened
  in a plain browser - a full-resolution export does not fit in the webview's memory.
- **Local-only API**: the sidecar listens on a fixed port, so `reject_foreign_origins` turns away any
  request carrying an `Origin` that is not the app itself, and every destructive route is a POST (a GET
  can be fired from a cross-site `<img>`, which sends no Origin at all).
- **Cache pruning**: on startup, `prune_orphaned_cache()` deletes `~/.alembic/cache/<session_id>/` for
  sessions that no longer exist - a schema bump wipes the rows but not the files.
- **Schema versioning**: `AppMetadata` table stores `schema_version`. When `CURRENT_SCHEMA_VERSION` (in `app.py`) changes, all sessions and embeddings are wiped on startup to avoid incompatible data.

## Development Commands

```bash
# Prerequisites: Rust (via rustup) and Python 3.12+
# If cargo is not in PATH, run: source ~/.cargo/env

# Linux system dependencies (Ubuntu/Debian)
sudo apt-get install -y pkg-config libglib2.0-dev libgtk-3-dev libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev libsoup-3.0-dev libayatana-appindicator3-dev librsvg2-dev libssl-dev patchelf libturbojpeg0-dev

# Setup Python environment
python3 -m venv .venv && source .venv/bin/activate && pip install -r app/requirements-dev.txt pyinstaller

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
