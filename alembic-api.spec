# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

# Platform-specific TurboJPEG binary
if sys.platform == 'linux':
    turbojpeg_binaries = [('/usr/lib/x86_64-linux-gnu/libturbojpeg.so.0', '.')]
elif sys.platform == 'darwin':
    import glob
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
    turbojpeg_binaries = [('C:/libjpeg-turbo64/bin/turbojpeg.dll', '.')]
else:
    turbojpeg_binaries = []

a = Analysis(
    ['app/run_server.py'],
    pathex=['app'],
    binaries=turbojpeg_binaries,
    datas=[],
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
        'flask_sqlalchemy',
        'exifread',
        'requests',
        'dotenv',
        'scipy.special._ufuncs_cxx',
        'scipy._lib.messagestream',
        'skimage',
        'skimage.io',
        'skimage._shared',
        'skimage._shared.geometry',
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
    [],
    exclude_binaries=True,
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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='alembic-api',
)
