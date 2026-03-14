#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- Detect platform and target triple ---
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux)
        case "$ARCH" in
            x86_64)  TARGET="x86_64-unknown-linux-gnu" ;;
            aarch64) TARGET="aarch64-unknown-linux-gnu" ;;
            *)       echo "Unsupported Linux arch: $ARCH"; exit 1 ;;
        esac
        EXE_SUFFIX=""
        ;;
    Darwin)
        case "$ARCH" in
            x86_64)  TARGET="x86_64-apple-darwin" ;;
            arm64)   TARGET="aarch64-apple-darwin" ;;
            *)       echo "Unsupported macOS arch: $ARCH"; exit 1 ;;
        esac
        EXE_SUFFIX=""
        ;;
    MINGW*|MSYS*|CYGWIN*)
        TARGET="x86_64-pc-windows-msvc"
        EXE_SUFFIX=".exe"
        ;;
    *)
        echo "Unsupported OS: $OS"
        exit 1
        ;;
esac

echo "==> Platform: $OS/$ARCH"
echo "==> Target triple: $TARGET"

cd "$PROJECT_ROOT"

# --- Step 1: Build Python sidecar with PyInstaller ---
echo "==> Building Python sidecar with PyInstaller..."
pyinstaller alembic-api.spec --noconfirm

# --- Step 2: Copy sidecar to src-tauri/binaries ---
BINARIES_DIR="src-tauri/binaries"
SIDECAR_NAME="alembic-api-${TARGET}${EXE_SUFFIX}"

echo "==> Copying sidecar to $BINARIES_DIR..."

# Remove old sidecar binary/symlink
rm -f "$BINARIES_DIR/$SIDECAR_NAME"

# Remove old _internal directory if present
rm -rf "$BINARIES_DIR/_internal"

# Copy the entire onedir output (binary + _internal/) into binaries/
cp -r dist/alembic-api/* "$BINARIES_DIR/"

# Rename the main binary to include the target triple
mv "$BINARIES_DIR/alembic-api${EXE_SUFFIX}" "$BINARIES_DIR/$SIDECAR_NAME"

echo "==> Sidecar ready: $BINARIES_DIR/$SIDECAR_NAME"

# --- Step 3: Build Tauri app ---
echo "==> Building Tauri application..."
cd "$PROJECT_ROOT"
cargo tauri build

echo "==> Build complete! Bundles are in src-tauri/target/release/bundle/"
