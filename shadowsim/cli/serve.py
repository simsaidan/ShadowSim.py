"""Serve the local ShadowSim builder page."""

import argparse
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from shadowsim.backends import listed_backends
from shadowsim.cli.run import run_page
from shadowsim.models.catalog import listed_model_terms, listed_models
from shadowsim.simulators.catalog import listed_simulators

_CATALOGS = {
    "/models": "models",
    "/simulators": "simulators",
    "/backends": "backends",
}

_SITE_DIR = Path(__file__).resolve().parent / "site"
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def _site_asset(url_path: str) -> tuple[Path, str] | None:
    """Map a request path to one file in the site directory.

    Args:
        url_path: URL path from the request, without the query string.

    Returns:
        The file and its content type, or ``None`` when the path is not a site asset.
    """
    relative = "index.html" if url_path == "/" else url_path.lstrip("/")
    if not relative or relative != Path(relative).name or relative.startswith("."):
        return None
    path = _SITE_DIR / relative
    content_type = _CONTENT_TYPES.get(path.suffix)
    if content_type is None or not path.is_file():
        return None
    return path, content_type


class _Handler(BaseHTTPRequestHandler):
    """Serve the builder page, list package choices, and run a posted selection."""

    def do_GET(self) -> None:
        """Return a site asset or a package catalog, or 404 for every other path."""
        path = urlsplit(self.path).path
        key = _CATALOGS.get(path)
        if key is not None:
            try:
                payload = {key: _load_catalog(key)}
            except Exception as exc:
                _send_json(self, 500, {"error": str(exc)})
                return
            _send_json(self, 200, payload)
            return
        asset = _site_asset(path)
        if asset is None:
            self.send_error(404)
            return
        asset_path, content_type = asset
        body = asset_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        """Run a posted selection, or 404 for every path other than ``/runs``."""
        if urlsplit(self.path).path != "/runs":
            self.send_error(404)
            return
        try:
            selection = _json_object(self._body())
        except ValueError as exc:
            _send_json(self, 400, {"error": str(exc)})
            return
        try:
            payload = run_page(selection)
        except ValueError as exc:
            _send_json(self, 400, {"error": str(exc)})
            return
        except Exception as exc:
            _send_json(self, 500, {"error": str(exc)})
            return
        _send_json(self, 200, payload)

    def _body(self) -> bytes:
        """Return the request body, or raise if its length is missing."""
        length = self.headers.get("Content-Length")
        if length is None:
            raise ValueError("request body must be JSON")
        try:
            size = int(length)
        except ValueError:
            raise ValueError("request body must be JSON") from None
        if size < 0:
            raise ValueError("request body must be JSON")
        return self.rfile.read(size)

    def log_message(self, format: str, *args: object) -> None:
        """Keep request logs off the terminal."""
        return


def _load_catalog(key: str) -> Any:
    """Return the current catalog for ``key``.

    The lookup stays in this function so tests can replace the loader.
    """
    if key == "models":
        return [*listed_models(), *listed_model_terms()]
    if key == "simulators":
        return listed_simulators()
    return listed_backends()


def _json_object(body: bytes) -> dict[str, Any]:
    """Parse ``body`` as a JSON object.

    Raises:
        ValueError: The body is not a JSON object.
    """
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise ValueError("request body must be JSON") from None
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _send_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    """Write ``payload`` as a JSON response."""
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    """Build the ``shadowsim`` argument parser."""
    parser = argparse.ArgumentParser(prog="shadowsim", description="ShadowSim commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve", help="Open the local builder page.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Address to bind (default: 127.0.0.1).")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000).")
    serve_parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    return parser


def serve(host: str, port: int, *, open_browser: bool) -> int:
    """Bind a local server and serve the builder page until interrupted.

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
