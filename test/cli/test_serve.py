"""Tests for the local builder page server."""

import json
import multiprocessing
import threading
import time
import urllib.error
import urllib.request
from http.server import HTTPServer
from typing import Any

import pytest

from shadowsim.cli.serve import _Handler, _park_until_killed, _send_json, _terminate_process, main, serve


def test_index_serves_the_builder_page():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/html")
            assert "ShadowSim.py Simulation Builder" in body
            assert 'src="/builder.js"' in body
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/styles.css") as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/css")
            assert ".board" in response.read().decode("utf-8")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/builder.js") as response:
            assert response.status == 200
            assert "javascript" in response.headers["Content-Type"]
            assert "Pick a model" in response.read().decode("utf-8")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/other")
        assert exc_info.value.code == 404
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/missing.js")
        assert missing.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_main_serve_uses_the_requested_bind(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    def fake_serve(host: str, port: int, *, open_browser: bool, allow_remote: bool) -> int:
        seen["host"] = host
        seen["port"] = port
        seen["open_browser"] = open_browser
        seen["allow_remote"] = allow_remote
        return 0

    monkeypatch.setattr("shadowsim.cli.serve.serve", fake_serve)
    assert main(["serve", "--host", "127.0.0.1", "--port", "8765", "--no-browser"]) == 0
    assert seen == {"host": "127.0.0.1", "port": 8765, "open_browser": False, "allow_remote": False}
    assert main(["serve", "--host", "0.0.0.0", "--allow-remote", "--no-browser"]) == 0
    assert seen["host"] == "0.0.0.0"
    assert seen["allow_remote"] is True


def test_main_opens_the_browser_by_default(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    def fake_serve(host: str, port: int, *, open_browser: bool, allow_remote: bool) -> int:
        seen["open_browser"] = open_browser
        return 0

    monkeypatch.setattr("shadowsim.cli.serve.serve", fake_serve)
    assert main(["serve"]) == 0
    assert seen["open_browser"] is True


def test_serve_rejects_an_invalid_port(capsys: pytest.CaptureFixture[str]):
    assert serve("127.0.0.1", 70000, open_browser=False) == 1
    assert serve("127.0.0.1", -1, open_browser=False) == 1
    assert "port must be between 0 and 65535" in capsys.readouterr().err


class _QuietServer(HTTPServer):
    """Stand in for ``HTTPServer`` without opening a socket."""

    def __init__(self, server_address: tuple[str, int], request_handler_class: type[_Handler]) -> None:
        self.server_address = server_address

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        raise KeyboardInterrupt

    def server_close(self) -> None:
        return None


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost", "[::1]"])
def test_serve_accepts_loopback_without_allow_remote(
    host: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", _QuietServer)
    assert serve(host, 8000, open_browser=False) == 0
    captured = capsys.readouterr()
    assert "refusing to bind" not in captured.err
    assert "warning:" not in captured.err
    assert "Serving ShadowSim at" in captured.out


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "example.com", ""])
def test_serve_refuses_a_non_loopback_host(
    host: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    opened: list[str] = []

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("should not bind")

    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", fail)
    monkeypatch.setattr("shadowsim.cli.serve.webbrowser.open", lambda url: opened.append(url) or True)
    assert serve(host, 8000, open_browser=True) == 1
    error = capsys.readouterr().err
    assert "refusing to bind" in error
    assert "--allow-remote" in error
    assert opened == []


def test_serve_warns_when_remote_bind_is_allowed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", _QuietServer)
    assert serve("0.0.0.0", 8000, open_browser=False, allow_remote=True) == 0
    captured = capsys.readouterr()
    assert "warning:" in captured.err
    assert "0.0.0.0" in captured.err
    assert "not authenticated" in captured.err
    assert "Serving ShadowSim at http://0.0.0.0:8000/" in captured.out


def test_serve_reports_a_busy_port(capsys: pytest.CaptureFixture[str]):
    busy = HTTPServer(("127.0.0.1", 0), _Handler)
    port = busy.server_address[1]
    try:
        assert serve("127.0.0.1", port, open_browser=False) == 1
    finally:
        busy.server_close()
    assert "could not bind" in capsys.readouterr().err


def test_serve_answers_then_stops(monkeypatch: pytest.MonkeyPatch):
    opened: list[str] = []
    monkeypatch.setattr("shadowsim.cli.serve.webbrowser.open", lambda url: opened.append(url) or True)

    started = threading.Event()
    servers: list[HTTPServer] = []

    class _RecordingServer(HTTPServer):
        def serve_forever(self, poll_interval: float = 0.5) -> None:
            servers.append(self)
            started.set()
            super().serve_forever(poll_interval)

    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", _RecordingServer)

    result: dict[str, int] = {}

    def run() -> None:
        result["code"] = serve("127.0.0.1", 0, open_browser=True)

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(timeout=2)
    server = servers[0]
    _host, port = server.server_address[:2]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
            assert b"ShadowSim.py Simulation Builder" in response.read()
    finally:
        server.shutdown()
        thread.join(timeout=5)
    assert result["code"] == 0
    assert opened == [f"http://127.0.0.1:{port}/"]


def test_serve_formats_an_ipv6_address_and_stops_on_interrupt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    class _IPv6Server(HTTPServer):
        def __init__(self, server_address: tuple[str, int], request_handler_class: type[_Handler]) -> None:
            super().__init__(("127.0.0.1", 0), request_handler_class)
            self.server_address = (b"::1", 4321)

        def serve_forever(self, poll_interval: float = 0.5) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", _IPv6Server)
    assert serve("127.0.0.1", 0, open_browser=False) == 0
    output = capsys.readouterr().out
    assert "http://[::1]:4321/" in output
    assert "Stopped." in output


def _exchange(port: int, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _open_server() -> tuple[Any, threading.Thread]:
    from shadowsim.cli.serve import HTTPServer as ThreadedServer

    server = ThreadedServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _close_server(server: Any, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_send_json_ignores_a_disconnected_client() -> None:
    class _Closed:
        def __init__(self) -> None:
            self.wfile = self

        def send_response(self, status: int) -> None:
            return None

        def send_header(self, name: str, value: str) -> None:
            return None

        def end_headers(self) -> None:
            return None

        def write(self, body: bytes) -> None:
            raise ConnectionResetError("closed")

    _send_json(_Closed(), 200, {"ok": True})  # type: ignore[arg-type]


def test_a_run_leaves_the_page_available_and_rejects_another(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    release = threading.Event()
    calls: list[object] = []

    def hold(selection: dict[str, object]) -> tuple[str, dict[str, bool]]:
        calls.append(selection)
        if len(calls) == 1:
            started.set()
            assert release.wait(timeout=5)
        return ("ok", {"ok": True})

    monkeypatch.setattr("shadowsim.cli.serve._run_in_child", hold)
    server, thread = _open_server()
    port = server.server_address[1]
    first: dict[str, tuple[int, bytes]] = {}

    def post_first() -> None:
        first["result"] = _exchange(port, "POST", "/runs", b"{}")

    poster = threading.Thread(target=post_first)
    poster.start()
    try:
        assert started.wait(timeout=2)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            assert response.status == 200
        status, body = _exchange(port, "POST", "/runs", b"{}")
        assert status == 409
        assert json.loads(body) == {"error": "a run is still finishing"}
        assert len(calls) == 1
        release.set()
        poster.join(timeout=5)
        assert first["result"] == (200, b'{"ok": true}')
        status, body = _exchange(port, "POST", "/runs", b'{"again": true}')
        assert status == 200
        assert json.loads(body) == {"ok": True}
        assert len(calls) == 2
    finally:
        release.set()
        poster.join(timeout=5)
        _close_server(server, thread)


def test_a_child_error_is_logged_and_hidden(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(selection: dict[str, object]) -> tuple[str, str]:
        return ("error", "RuntimeError: boom\n")

    monkeypatch.setattr("shadowsim.cli.serve._run_in_child", fail)
    server, thread = _open_server()
    port = server.server_address[1]
    try:
        status, body = _exchange(port, "POST", "/runs", b"{}")
    finally:
        _close_server(server, thread)
    assert status == 500
    assert json.loads(body) == {"error": "internal error"}
    assert "boom" in capsys.readouterr().err
    assert b"boom" not in body


def test_cancel_without_a_run_is_not_found() -> None:
    server, thread = _open_server()
    port = server.server_address[1]
    try:
        status, _body = _exchange(port, "POST", "/runs/cancel")
        assert status == 404
    finally:
        _close_server(server, thread)


def test_terminate_process_ends_the_group() -> None:
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    started = context.Event()
    process = context.Process(target=_park_until_killed, args=(child, started), daemon=True)
    process.start()
    child.close()
    try:
        assert started.wait(timeout=15)
        _terminate_process(process)
        assert not process.is_alive()
        assert process.exitcode is not None and process.exitcode < 0
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=2)
        parent.close()
        process.join(timeout=2)
        if not process.is_alive():
            process.close()


def test_cancel_stops_the_child_and_frees_the_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    from shadowsim.cli import serve as serve_cli

    context = multiprocessing.get_context("spawn")
    ready = context.Event()

    def spawn(selection: dict[str, object]) -> tuple[multiprocessing.Process, Any]:
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=_park_until_killed, args=(child, ready), daemon=True)
        process.start()
        child.close()
        return process, parent

    monkeypatch.setattr(serve_cli, "_spawn_page", spawn)
    server, thread = _open_server()
    port = server.server_address[1]
    outcome: dict[str, tuple[int, bytes]] = {}

    def post_run() -> None:
        outcome["result"] = _exchange(port, "POST", "/runs", b"{}")

    poster = threading.Thread(target=post_run)
    poster.start()
    try:
        assert ready.wait(timeout=15)
        status, body = _exchange(port, "POST", "/runs/cancel")
        assert status == 204
        assert body == b""
        poster.join(timeout=5)
        assert outcome["result"][0] == 200
        assert json.loads(outcome["result"][1]) == {"cancelled": True}
        deadline = time.monotonic() + 2
        while serve_cli._slot.running.locked() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not serve_cli._slot.running.locked()
        assert serve_cli._slot.phase is serve_cli._RunPhase.IDLE
    finally:
        poster.join(timeout=5)
        _close_server(server, thread)
