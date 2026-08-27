# -*- mode: python ; coding: utf-8 -*-
import glob
import os
import platform
import sys

block_cipher = None

# Platform-specific TurboJPEG binary. utils.py instantiates TurboJPEG at import time, so a sidecar
# built without this library does not start at all - which is why a miss below stops the build.
if sys.platform == 'linux':
    # The multiarch directory is named after the architecture, so an aarch64 build finds nothing
    # under the x86_64 path this used to hardcode.
    linux_paths = [
        f'/usr/lib/{platform.machine()}-linux-gnu/libturbojpeg.so.0',
        '/usr/lib64/libturbojpeg.so.0',
        '/usr/lib/libturbojpeg.so.0',
        '/usr/local/lib/libturbojpeg.so.0',
    ]
    linux_paths += sorted(glob.glob('/usr/lib/*/libturbojpeg.so.0'))
    found = next((path for path in linux_paths if os.path.exists(path)), None)
    turbojpeg_binaries = [(found, '.')] if found else []
elif sys.platform == 'darwin':
    # ARM Mac (Apple Silicon)
    arm_path = '/opt/homebrew/lib/libturbojpeg.dylib'
    # Intel Mac
    intel_path = '/usr/local/lib/libturbojpeg.dylib'
    # Homebrew cellar fallback
    cellar_paths = glob.glob('/opt/homebrew/Cellar/jpeg-turbo/*/lib/libturbojpeg.dylib')
    if os.path.exists(arm_path):
        turbojpeg_binaries = [(arm_path, '.')]
    elif os.path.exists(intel_path):
        turbojpeg_binaries = [(intel_path, '.')]
    elif cellar_paths:
        turbojpeg_binaries = [(cellar_paths[0], '.')]
    else:
        turbojpeg_binaries = []
elif sys.platform == 'win32':
    windows_paths = [
        'C:/libjpeg-turbo64/bin/turbojpeg.dll',
        'C:/libjpeg-turbo/bin/turbojpeg.dll',
    ]
    found = next((path for path in windows_paths if os.path.exists(path)), None)
    turbojpeg_binaries = [(found, '.')] if found else []
else:
    turbojpeg_binaries = []

if not turbojpeg_binaries and sys.platform in ('linux', 'darwin', 'win32'):
    raise SystemExit(
        f'libturbojpeg not found on {sys.platform}. Install it (libturbojpeg0-dev, brew install '
        'jpeg-turbo, or the libjpeg-turbo installer) before building the sidecar.'
    )

a = Analysis(
    ['app/run_server.py'],
    pathex=['app'],
    binaries=turbojpeg_binaries,
    datas=[('app/onnx_checkpoints/efficientnet_b0.onnx', 'onnx_checkpoints')],
    hiddenimports=[
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.dialects.sqlite.pysqlite',
        'numpy',
        'cv2',
        'rawpy',
        'PIL',
        'PIL.Image',
        'PIL.JpegImagePlugin',
        'PIL.PngImagePlugin',
        'PIL.TiffImagePlugin',
        'flask_cors',
        'waitress',
        'flask_sqlalchemy',
        'onnxruntime',
        'exifread',
        'dotenv',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    exclude_binaries=False,
    name='alembic-api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
