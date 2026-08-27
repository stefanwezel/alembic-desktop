import logging
import os
import socket
import sys

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

PORT = 3001


def bind_loopback(family, host):
    """A socket bound to one loopback address, closed again if the bind fails."""
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            # Keep this one off the v4 address, which is already spoken for below.
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock.bind((host, PORT))
    except OSError:
        sock.close()
        raise
    return sock


def listening_sockets():
    """The v4 loopback, plus the v6 one where the host has it.

    The frontend asks for http://localhost:3001 and Windows resolves that name to ::1 before
    127.0.0.1, so listening on the v4 address alone costs every single request a refused connection
    first. Binding the two here rather than handing waitress both addresses is what keeps a host
    with IPv6 switched off working at all: waitress leaves an already-bound socket open when a later
    one fails, so the port would be taken and nothing could listen on it afterwards.
    """
    sockets = [bind_loopback(socket.AF_INET, '127.0.0.1')]
    try:
        sockets.append(bind_loopback(socket.AF_INET6, '::1'))
    except OSError as e:
        logging.warning(f"No IPv6 loopback to listen on ({e}); serving on 127.0.0.1 only.")
    return sockets


def main():
    cache_dir = os.environ.get('MEDIA_FOLDER', os.path.join(os.path.expanduser('~'), '.alembic', 'cache'))
    os.makedirs(cache_dir, exist_ok=True)

    # waitress, not the Werkzeug development server: that one speaks HTTP/1.0 and hangs up after
    # every response, so each request needs a fresh connection that is torn down underneath the
    # client. Chromium - the engine behind the Windows webview - silently retries a GET when that
    # goes wrong but never a POST, which showed up as every read working while every write appeared
    # to fail, even though the server had already applied it.
    from waitress import serve

    serve(app, sockets=listening_sockets(), threads=8, ident='Alembic')


if __name__ == '__main__':
    main()
