"""Tests for the local blank-page server."""

import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

import pytest

from shadowsim.cli.serve import _Handler, main, serve


def test_index_is_a_blank_page():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/html")
            assert "<body></body>" in body
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/other")
        assert exc_info.value.code == 404
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


def test_serve_rejects_an_invalid_port():
    assert serve("127.0.0.1", 70000, open_browser=False) == 1
