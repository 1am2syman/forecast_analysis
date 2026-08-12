#!/usr/bin/env python3
"""Single-file static server: responds to any GET with index.html.
Prefix-proof, so it works behind a Tailscale funnel path route."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Load the page up front; fail loudly with a clear message if it's missing.
try:
    with open(os.path.join(HERE, "index.html"), "rb") as fh:
        HTML = fh.read()
except OSError as exc:
    sys.stderr.write("fatal: cannot read index.html: %s\n" % exc)
    sys.exit(1)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(HTML)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, format, *args):  # noqa: A002 - matches base class signature
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))


def _read_port(default=8767):
    raw = os.environ.get("PORT", str(default))
    try:
        port = int(raw)
    except (TypeError, ValueError):
        sys.stderr.write("warning: invalid PORT %r, using %d\n" % (raw, default))
        port = default
    return port


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", _read_port()), Handler).serve_forever()
