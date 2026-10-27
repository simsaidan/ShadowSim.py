"""Serve the local ShadowSim builder page."""

import argparse
import enum
import ipaddress
import json
import multiprocessing
import os
import signal
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer as _HTTPServer
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from socketserver import ThreadingMixIn
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
_POLL_SECONDS = 0.2
_KILL_AFTER = 2.0
_BUSY = "a run is still finishing"


class _RunPhase(enum.Enum):
    """Whether a posted run currently owns the server's one slot."""

    IDLE = "idle"
    RUNNING = "running"


class _Slot:
    """The single simulation the page is allowed to have in flight."""

    def __init__(self) -> None:
        self.phase = _RunPhase.IDLE
        self.process: BaseProcess | None = None
        self.cancel = threading.Event()
        self.guard = threading.Lock()
        self.running = threading.Lock()


_slot = _Slot()


class HTTPServer(ThreadingMixIn, _HTTPServer):
    """Serve each request on a daemon thread so one run does not block the page."""

    daemon_threads = True


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
                _send_internal_error(self, exc)
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
        """Run a posted selection, or cancel the run that is in flight.

        ``POST /runs/cancel`` stops that child process. A second ``POST /runs``
        while it is still going receives 409 and does not start another one.
        """
        path = urlsplit(self.path).path
        if path == "/runs/cancel":
            if not _cancel_run():
                self.send_error(404)
                return
            _send_empty(self, 204)
            return
        if path != "/runs":
            self.send_error(404)
            return
        try:
            selection = _json_object(self._body())
        except ValueError as exc:
            _send_json(self, 400, {"error": str(exc)})
            return
        if not _slot.running.acquire(blocking=False):
            _send_json(self, 409, {"error": _BUSY})
            return
        with _slot.guard:
            _slot.phase = _RunPhase.RUNNING
            _slot.cancel.clear()
        try:
            try:
                outcome = _run_in_child(selection)
            except Exception as exc:
                _send_internal_error(self, exc)
                return
            _finish_run(self, outcome)
        finally:
            with _slot.guard:
                _slot.phase = _RunPhase.IDLE
                _slot.process = None
                _slot.cancel.clear()
            _slot.running.release()

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


def _detach_process_group() -> None:
    """Move this process into its own group so cancel can stop its workers too."""
    if os.name == "nt":
        return
    try:
        os.setsid()
    except OSError:
        return


def _run_page_in_child(selection: dict[str, Any], connection: Connection) -> None:
    """Run one selection and send ``(kind, payload)`` to the parent."""
    _detach_process_group()
    try:
        try:
            payload = run_page(selection)
        except ValueError as exc:
            message: tuple[str, Any] = ("invalid", str(exc))
        except Exception as exc:
            message = ("error", "".join(traceback.format_exception(exc)))
        else:
            message = ("ok", payload)
        try:
            connection.send(message)
        except (BrokenPipeError, EOFError, OSError):
            return
    finally:
        connection.close()


def _park_until_killed(connection: Connection, started: Any) -> None:
    """Hold a process group open until it is killed.

    Sends nothing on ``connection``. ``started`` is set after the group exists
    so a test can terminate it the same way a run is cancelled.
    """
    _detach_process_group()
    started.set()
    try:
        while True:
            time.sleep(_POLL_SECONDS)
    finally:
        connection.close()


def _spawn_page(selection: dict[str, Any]) -> tuple[BaseProcess, Connection]:
    """Start ``run_page`` in a spawned process and return its result pipe."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_run_page_in_child,
        args=(selection, child),
        daemon=True,
        name="shadowsim-run",
    )
    try:
        process.start()
    except Exception:
        parent.close()
        child.close()
        raise
    child.close()
    return process, parent


def _run_in_child(selection: dict[str, Any]) -> tuple[str, Any]:
    """Run ``selection`` in one child and return ``(kind, payload)``.

    ``kind`` is ``ok``, ``invalid``, ``error``, or ``cancelled``.
    """
    process, parent = _spawn_page(selection)
    with _slot.guard:
        _slot.process = process
        cancelled = _slot.cancel.is_set()
    try:
        if cancelled:
            _terminate_process(process)
            return ("cancelled", None)
        return _wait_for_result(process, parent)
    finally:
        with _slot.guard:
            _slot.process = None
        parent.close()
        if process.is_alive():
            _terminate_process(process)
        else:
            process.join(timeout=_KILL_AFTER)


def _wait_for_result(process: BaseProcess, parent: Connection) -> tuple[str, Any]:
    """Return the child's message, or cancelled when the process is killed."""
    while process.is_alive():
        if _slot.cancel.is_set():
            _terminate_process(process)
            return ("cancelled", None)
        try:
            arrived = parent.poll(_POLL_SECONDS)
        except OSError:
            break
        if arrived:
            if _slot.cancel.is_set():
                _terminate_process(process)
                return ("cancelled", None)
            break
    message = _receive_message(parent)
    if message is None:
        return _result_after_exit(process)
    return _decode_message(message)


def _receive_message(parent: Connection) -> object | None:
    """Read one piped result, waiting briefly for a message sent as the child exits."""
    for _ in range(20):
        try:
            if parent.poll(0.05):
                return parent.recv()
        except (EOFError, OSError):
            return None
    return None


def _result_after_exit(process: BaseProcess) -> tuple[str, Any]:
    """Return cancelled when a signal stopped the child, otherwise an internal error."""
    code = process.exitcode
    if code is not None and code < 0:
        return ("cancelled", None)
    return ("error", "the run ended without a result\n")


def _decode_message(message: object) -> tuple[str, Any]:
    """Return a child message the handler understands, or an internal error."""
    if isinstance(message, tuple) and len(message) == 2 and isinstance(message[0], str):
        kind, payload = message
        if kind == "ok" and isinstance(payload, dict):
            return ("ok", payload)
        if kind == "invalid" and isinstance(payload, str):
            return ("invalid", payload)
        if kind == "error" and isinstance(payload, str):
            return ("error", payload)
    return ("error", "the run ended without a result\n")


def _signal_group(process: BaseProcess, *, kill: bool) -> None:
    """Signal the child's process group, or the child itself when it has no group."""
    if not process.is_alive():
        return
    pid = process.pid
    if pid is None:
        return
    if os.name == "nt":
        if kill:
            process.kill()
        else:
            process.terminate()
        return
    try:
        os.killpg(pid, signal.SIGKILL if kill else signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        if kill:
            process.kill()
        else:
            process.terminate()


def _terminate_process(process: BaseProcess) -> None:
    """Stop ``process`` and its group, then kill it if it is still alive."""
    _signal_group(process, kill=False)
    process.join(_KILL_AFTER)
    if not process.is_alive():
        return
    _signal_group(process, kill=True)
    process.join(_KILL_AFTER)


def _cancel_run() -> bool:
    """Stop the in-flight run. Return whether one was running."""
    with _slot.guard:
        if _slot.phase is _RunPhase.IDLE:
            return False
        _slot.cancel.set()
        process = _slot.process
    if process is not None:
        _terminate_process(process)
    return True


def _finish_run(handler: BaseHTTPRequestHandler, outcome: tuple[str, Any]) -> None:
    """Write the HTTP response for one child outcome."""
    kind, payload = outcome
    if kind == "ok" and isinstance(payload, dict):
        _send_json(handler, 200, payload)
        return
    if kind == "invalid" and isinstance(payload, str):
        _send_json(handler, 400, {"error": payload})
        return
    if kind == "cancelled":
        _send_json(handler, 200, {"cancelled": True})
        return
    text = payload if isinstance(payload, str) else "the run ended without a result\n"
    _log_child_error(text)
    _send_json(handler, 500, {"error": "internal error"})


def _log_child_error(text: str) -> None:
    """Print a child failure on stderr. The client receives a fixed message instead."""
    if not text.endswith("\n"):
        text = f"{text}\n"
    print(text, file=sys.stderr, end="")
    sys.stderr.flush()


def _is_loopback_host(host: str) -> bool:
    """Return whether ``host`` is localhost or a loopback IP address.

    Unspecified addresses such as ``0.0.0.0`` and ``::``, every other IP, and
    every other name are not loopback.
    """
    if host.lower().rstrip(".") == "localhost":
        return True
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    candidate = candidate.split("%", 1)[0]
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return address.is_loopback


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
    """Write ``payload`` as a JSON response. A client that already left is ignored."""
    body = json.dumps(payload).encode("utf-8")
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    except ConnectionError:
        return


def _send_empty(handler: BaseHTTPRequestHandler, status: int) -> None:
    """Write a response with no body. A client that already left is ignored."""
    try:
        handler.send_response(status)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
    except ConnectionError:
        return


def _send_internal_error(handler: BaseHTTPRequestHandler, exc: BaseException) -> None:
    """Send a fixed 500 and print ``exc`` on stderr.

    The response omits ``exc`` so a client does not receive local paths or
    importer details from an unexpected failure.

    Args:
        handler: Request that failed.
        exc: Unexpected failure. Its traceback is written to stderr.
    """
    traceback.print_exception(exc, file=sys.stderr)
    sys.stderr.flush()
    _send_json(handler, 500, {"error": "internal error"})


def build_parser() -> argparse.ArgumentParser:
    """Build the ``shadowsim`` argument parser."""
    parser = argparse.ArgumentParser(prog="shadowsim", description="ShadowSim commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve", help="Open the local builder page.")
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Address to bind (default: 127.0.0.1). A non-loopback address requires --allow-remote.",
    )
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000).")
    serve_parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Bind a non-loopback address. The builder does not authenticate requests.",
    )
    serve_parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    return parser


def serve(host: str, port: int, *, open_browser: bool, allow_remote: bool = False) -> int:
    """Bind a server and serve the builder page until interrupted.

    Args:
        host: Address to bind.
        port: TCP port to bind.
        open_browser: Open the page in the default browser after the server starts.
        allow_remote: Permit a non-loopback ``host``. Without this, such an address
            is refused because requests, including ``POST /runs``, are not authenticated.

    Returns:
        Process exit code. ``0`` after a clean interrupt, ``1`` if the port is invalid,
        the address is not loopback and ``allow_remote`` is false, or the address
        cannot be bound.
    """
    if port < 0 or port > 65535:
        print(f"error: port must be between 0 and 65535, got {port}", file=sys.stderr)
        return 1
    if not allow_remote and not _is_loopback_host(host):
        print(
            f"error: refusing to bind {host}: the builder does not authenticate requests. "
            "Pass --allow-remote to listen on a non-loopback address.",
            file=sys.stderr,
        )
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
    if not _is_loopback_host(host):
        print(
            f"warning: {host} is not a loopback address. Requests are not authenticated.",
            file=sys.stderr,
            flush=True,
        )
    print(f"Serving ShadowSim at {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        _cancel_run()
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the ``shadowsim`` command-line interface."""
    args = build_parser().parse_args(argv)
    return serve(
        args.host,
        args.port,
        open_browser=not args.no_browser,
        allow_remote=args.allow_remote,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
