"""Serve a blank local ShadowSim page."""

import argparse
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

_BLANK_PAGE = b"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ShadowSim</title>
</head>
<body></body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    """Serve the blank index page."""

    def do_GET(self) -> None:
        """Return the blank page for ``/`` and 404 for every other path."""
        if urlsplit(self.path).path != "/":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(_BLANK_PAGE)))
        self.end_headers()
        self.wfile.write(_BLANK_PAGE)

    def log_message(self, format: str, *args: object) -> None:
        """Keep request logs off the terminal."""
        return


def build_parser() -> argparse.ArgumentParser:
    """Build the ``shadowsim`` argument parser."""
    parser = argparse.ArgumentParser(prog="shadowsim", description="ShadowSim commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve", help="Open a blank local page.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Address to bind (default: 127.0.0.1).")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000).")
    serve_parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    return parser


def serve(host: str, port: int, *, open_browser: bool) -> int:
    """Bind a local server and serve the blank page until interrupted.

    Args:
        host: Address to bind.
        port: TCP port to bind.
        open_browser: Open the page in the default browser after the server starts.

    Returns:
        Process exit code. ``0`` after a clean interrupt, ``1`` if the port is invalid
        or the address cannot be bound.
    """
    if port < 0 or port > 65535:
        print(f"error: port must be between 0 and 65535, got {port}", file=sys.stderr)
        return 1
    try:
        server = HTTPServer((host, port), _Handler)
    except OSError as exc:
        print(f"error: could not bind {host}:{port}: {exc}", file=sys.stderr)
        return 1

    raw_host, bound_port = server.server_address[:2]
    bound_host = raw_host.decode() if isinstance(raw_host, bytes) else raw_host
    display_host = f"[{bound_host}]" if ":" in bound_host else bound_host
    url = f"http://{display_host}:{bound_port}/"
    print(f"Serving ShadowSim at {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the ``shadowsim`` command-line interface."""
    args = build_parser().parse_args(argv)
    return serve(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
