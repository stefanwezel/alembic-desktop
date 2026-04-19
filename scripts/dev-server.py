"""Dev HTTP server with cache-control: no-store for hot-reload during development."""

import http.server
import sys
import os


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    directory = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    os.chdir(directory)
    with http.server.HTTPServer(("", port), NoCacheHandler) as httpd:
        httpd.serve_forever()
