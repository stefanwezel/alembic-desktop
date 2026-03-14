import sys
import os

# When running as a PyInstaller bundle, set up paths
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    # Add bundle dir to LD_LIBRARY_PATH so bundled libturbojpeg.so.0 is found
    # turbojpeg.py's __find_turbojpeg() explicitly checks LD_LIBRARY_PATH on Linux
    ld_path = os.environ.get('LD_LIBRARY_PATH', '')
    os.environ['LD_LIBRARY_PATH'] = f"{bundle_dir}:{ld_path}" if ld_path else bundle_dir

    os.environ.setdefault('MEDIA_FOLDER', os.path.join(os.path.expanduser('~'), '.alembic', 'cache'))
    os.environ.setdefault('APP_SECRET_KEY', 'desktop-app-secret-key')

from app import app


def main():
    cache_dir = os.environ.get('MEDIA_FOLDER', os.path.join(os.path.expanduser('~'), '.alembic', 'cache'))
    os.makedirs(cache_dir, exist_ok=True)
    app.run(host='127.0.0.1', port=3001, debug=False)


if __name__ == '__main__':
    main()
