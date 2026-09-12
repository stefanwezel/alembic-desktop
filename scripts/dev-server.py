"""Dev HTTP server with cache-control: no-store for hot-reload during development.

It also frees the ports a previous `cargo tauri dev` can leave occupied - the one it serves the
frontend on, and the one the sidecar takes - which is why this holds the logic rather than a shell
one-liner in tauri.conf.json: fuser, pkill and lsof all exist on exactly the platforms Windows is
not, so that one-liner only ever worked on Linux.
"""

import http.server
import os
import subprocess
import sys

API_PORT = 3001


def windows_listener_pids(port):
    """PIDs listening on `port`, read out of netstat - the only such mapping Windows ships with."""
    netstat = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True)
    pids = set()
    for line in netstat.stdout.splitlines():
        columns = line.split()
        # Proto, local address, foreign address, state, PID
        if len(columns) == 5 and columns[3] == "LISTENING" and columns[1].endswith(f":{port}"):
            pids.add(columns[4])
    return pids - {"0", "4"}  # System holds those two; never ours to kill


def free_port(port):
    """Kill whatever is still listening on `port` from an earlier run. Best effort."""
    try:
        if os.name == "nt":
            for pid in windows_listener_pids(port):
                subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
        else:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    except OSError as error:
        # Neither fuser nor netstat is everywhere. A port left occupied is a nuisance to sort out by
        # hand, not a reason to leave the dev server unstarted.
        print(f"Could not free port {port}: {error}", file=sys.stderr)


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    directory = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    for stale_port in (port, API_PORT):
        free_port(stale_port)
    os.chdir(directory)
    # Loopback only: binding every interface has the Windows firewall ask for permission that a dev
    # server serving a local webview has no use for.
    with http.server.HTTPServer(("127.0.0.1", port), NoCacheHandler) as httpd:
        httpd.serve_forever()
