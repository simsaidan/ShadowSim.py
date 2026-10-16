"""Tests for the local builder page server."""

import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

import pytest

from shadowsim.cli.serve import _Handler, main, serve


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

    def fake_serve(host: str, port: int, *, open_browser: bool) -> int:
        seen["host"] = host
        seen["port"] = port
        seen["open_browser"] = open_browser
        return 0

    monkeypatch.setattr("shadowsim.cli.serve.serve", fake_serve)
    assert main(["serve", "--host", "127.0.0.1", "--port", "8765", "--no-browser"]) == 0
    assert seen == {"host": "127.0.0.1", "port": 8765, "open_browser": False}


def test_main_opens_the_browser_by_default(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    def fake_serve(host: str, port: int, *, open_browser: bool) -> int:
        seen["open_browser"] = open_browser
        return 0

    monkeypatch.setattr("shadowsim.cli.serve.serve", fake_serve)
    assert main(["serve"]) == 0
    assert seen["open_browser"] is True


def test_serve_rejects_an_invalid_port(capsys: pytest.CaptureFixture[str]):
    assert serve("127.0.0.1", 70000, open_browser=False) == 1
    assert serve("127.0.0.1", -1, open_browser=False) == 1
    assert "port must be between 0 and 65535" in capsys.readouterr().err


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
