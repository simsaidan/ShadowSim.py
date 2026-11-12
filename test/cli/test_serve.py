"""Tests for the local builder page server."""

import json
import multiprocessing
import shutil
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import HTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from shadowsim.cli.serve import (
    _MAX_AUTH_BODY_BYTES,
    _Handler,
    _park_until_killed,
    _read_auth_body,
    _send_json,
    _terminate_process,
    main,
    serve,
)


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
            assert body.index('src="/checks.js"') < body.index('src="/builder.js"')
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/styles.css") as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/css")
            assert ".board" in response.read().decode("utf-8")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/checks.js") as response:
            assert response.status == 200
            assert "javascript" in response.headers["Content-Type"]
            assert "previewText" in response.read().decode("utf-8")
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

    def fake_serve(
        host: str,
        port: int,
        *,
        open_browser: bool,
        allow_remote: bool,
        output_dir: str = "results",
        tls_cert: str | None = None,
        tls_key: str | None = None,
    ) -> int:
        seen["host"] = host
        seen["port"] = port
        seen["open_browser"] = open_browser
        seen["allow_remote"] = allow_remote
        seen["output_dir"] = output_dir
        seen["tls_cert"] = tls_cert
        seen["tls_key"] = tls_key
        return 0

    monkeypatch.setattr("shadowsim.cli.serve.serve", fake_serve)
    assert main(["serve", "--host", "127.0.0.1", "--port", "8765", "--no-browser"]) == 0
    assert seen == {
        "host": "127.0.0.1",
        "port": 8765,
        "open_browser": False,
        "allow_remote": False,
        "output_dir": "results",
        "tls_cert": None,
        "tls_key": None,
    }
    assert main(["serve", "--host", "0.0.0.0", "--allow-remote", "--no-browser"]) == 0
    assert seen["host"] == "0.0.0.0"
    assert seen["allow_remote"] is True
    assert main(["serve", "--output-dir", "runs", "--no-browser"]) == 0
    assert seen["output_dir"] == "runs"
    assert main(["serve", "--tls-cert", "cert.pem", "--tls-key", "key.pem", "--no-browser"]) == 0
    assert seen["tls_cert"] == "cert.pem"
    assert seen["tls_key"] == "key.pem"


def test_main_opens_the_browser_by_default(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    def fake_serve(
        host: str,
        port: int,
        *,
        open_browser: bool,
        allow_remote: bool,
        output_dir: str = "results",
        tls_cert: str | None = None,
        tls_key: str | None = None,
    ) -> int:
        seen["open_browser"] = open_browser
        seen["output_dir"] = output_dir
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
    assert "Serving ShadowSim at http://" in captured.out
    assert "?token=" in captured.out
    assert "Startup token:" not in captured.out


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


def test_serve_refuses_remote_without_tls(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("should not bind")

    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", fail)
    assert serve("0.0.0.0", 8000, open_browser=False, allow_remote=True) == 1
    error = capsys.readouterr().err
    assert "refusing to bind" in error
    assert "cleartext" in error
    assert "--tls-cert" in error


@pytest.mark.parametrize(("tls_cert", "tls_key"), [("cert.pem", None), (None, "key.pem")])
def test_serve_refuses_a_single_tls_file(
    tls_cert: str | None,
    tls_key: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("should not bind")

    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", fail)
    assert serve("127.0.0.1", 8000, open_browser=False, tls_cert=tls_cert, tls_key=tls_key) == 1
    assert "must be passed together" in capsys.readouterr().err


def test_serve_prints_a_remote_https_url_without_the_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    created: list[_QuietServer] = []
    opened: list[str] = []

    class _RecordingQuiet(_QuietServer):
        def __init__(self, server_address: tuple[str, int], request_handler_class: type[_Handler]) -> None:
            super().__init__(server_address, request_handler_class)
            created.append(self)

    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", _RecordingQuiet)
    monkeypatch.setattr("shadowsim.cli.serve._server_tls", lambda certfile, keyfile: object())
    monkeypatch.setattr("shadowsim.cli.serve._install_tls", lambda server, context: None)
    monkeypatch.setattr("shadowsim.cli.serve.webbrowser.open", lambda url: opened.append(url) or True)
    assert (
        serve(
            "0.0.0.0",
            8000,
            open_browser=True,
            allow_remote=True,
            tls_cert="cert.pem",
            tls_key="key.pem",
        )
        == 0
    )
    captured = capsys.readouterr()
    assert "warning:" in captured.err
    assert "0.0.0.0" in captured.err
    assert "startup token" in captured.err
    url = "https://0.0.0.0:8000/"
    assert f"Serving ShadowSim at {url}" in captured.out
    assert "?token=" not in captured.out
    token_line = next(line for line in captured.out.splitlines() if line.startswith("Startup token: "))
    assert token_line.removeprefix("Startup token: ")
    assert opened == [url]
    assert created[0].tls is True
    assert created[0].accept_query_token is False


def test_serve_uses_https_on_loopback_when_tls_files_are_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from shadowsim.cli.serve import HTTPServer as ThreadedServer

    contexts: list[Any] = []
    servers: list[ThreadedServer] = []

    class _Context:
        def __init__(self, protocol: int) -> None:
            self.protocol = protocol
            self.minimum_version: ssl.TLSVersion | None = None
            self.loaded: tuple[object, object] | None = None
            self.server_side = False
            contexts.append(self)

        def load_cert_chain(self, certfile: object, keyfile: object) -> None:
            self.loaded = (certfile, keyfile)

        def wrap_socket(self, sock: socket.socket, server_side: bool = False) -> socket.socket:
            self.server_side = server_side
            return sock

    class _Stop(ThreadedServer):
        def serve_forever(self, poll_interval: float = 0.5) -> None:
            servers.append(self)
            raise KeyboardInterrupt

    monkeypatch.setattr("shadowsim.cli.serve.ssl.SSLContext", _Context)
    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", _Stop)
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    assert serve("127.0.0.1", 0, open_browser=False, tls_cert=cert, tls_key=key) == 0
    output = capsys.readouterr().out
    url_line = next(line for line in output.splitlines() if line.startswith("Serving ShadowSim at "))
    assert url_line.startswith("Serving ShadowSim at https://127.0.0.1:")
    assert "?token=" in url_line
    assert "Startup token:" not in output
    assert contexts[0].protocol == ssl.PROTOCOL_TLS_SERVER
    assert contexts[0].minimum_version == ssl.TLSVersion.TLSv1_2
    assert contexts[0].loaded == (cert, key)
    assert contexts[0].server_side is True
    assert servers[0].tls is True
    assert servers[0].accept_query_token is True


def test_serve_closes_the_socket_when_the_certificate_cannot_be_loaded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from shadowsim.cli.serve import HTTPServer as ThreadedServer

    created: list[ThreadedServer] = []

    class _Recording(ThreadedServer):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", _Recording)
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("not a certificate\n")
    key.write_text("not a key\n")
    assert serve("127.0.0.1", 0, open_browser=False, tls_cert=cert, tls_key=key) == 1
    captured = capsys.readouterr()
    assert "could not load TLS certificate" in captured.err
    assert "Serving ShadowSim" not in captured.out
    assert created[0].socket.fileno() == -1


def _certificate(directory: Path) -> tuple[Path, Path]:
    """Return a throwaway certificate and key written under ``directory``."""
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl is required to generate a throwaway certificate")
    cert = directory / "cert.pem"
    key = directory / "key.pem"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return cert, key


def _https(
    opener: urllib.request.OpenerDirector,
    port: int,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any, bytes]:
    request_headers = dict(headers or {})
    if body is not None:
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request = urllib.request.Request(
        f"https://127.0.0.1:{port}{path}",
        data=body,
        headers=request_headers,
        method="POST" if body is not None else "GET",
    )
    try:
        with opener.open(request, timeout=15) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def test_a_remote_server_completes_the_token_exchange_over_tls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from shadowsim.cli.serve import HTTPServer as ThreadedServer

    cert, key = _certificate(tmp_path)
    started = threading.Event()
    servers: list[ThreadedServer] = []

    class _Recording(ThreadedServer):
        def serve_forever(self, poll_interval: float = 0.5) -> None:
            servers.append(self)
            started.set()
            super().serve_forever(poll_interval)

    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", _Recording)
    result: dict[str, int] = {}

    def run() -> None:
        result["code"] = serve(
            "0.0.0.0",
            0,
            open_browser=False,
            allow_remote=True,
            tls_cert=cert,
            tls_key=key,
        )

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert started.wait(timeout=5)
        server = servers[0]
        port = server.server_address[1]
        token = server.token
        assert isinstance(token, str) and token
        assert server.tls is True
        assert server.accept_query_token is False
        output = capsys.readouterr().out
        url_line = next(line for line in output.splitlines() if line.startswith("Serving ShadowSim at "))
        assert url_line == f"Serving ShadowSim at https://0.0.0.0:{port}/"
        assert f"Startup token: {token}" in output

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), _NoRedirect)
        status, _headers, body = _https(opener, port, "/")
        assert status == 200
        assert b'action="/auth"' in body
        assert token.encode() not in body

        status, headers, body = _https(opener, port, "/auth", f"token={token}".encode())
        assert status == 303
        assert headers["Location"] == "/"
        assert headers["Set-Cookie"] == f"shadowsim-token={token}; HttpOnly; SameSite=Strict; Secure; Path=/"
        assert body == b""

        status, _headers, body = _https(opener, port, "/", headers={"Cookie": f"shadowsim-token={token}"})
        assert status == 200
        assert b"ShadowSim.py Simulation Builder" in body
    finally:
        if servers:
            servers[0].shutdown()
        thread.join(timeout=5)
    assert result["code"] == 0


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
    prefix = f"http://127.0.0.1:{port}/?token="
    try:
        assert len(opened) == 1
        assert opened[0].startswith(prefix)
        token = opened[0].removeprefix(prefix)
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/",
            headers={"Cookie": f"shadowsim-token={token}"},
        )
        with urllib.request.urlopen(request) as response:
            assert b"ShadowSim.py Simulation Builder" in response.read()
    finally:
        server.shutdown()
        thread.join(timeout=5)
    assert result["code"] == 0


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


def _exchange(
    port: int,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    request_headers = dict(headers or {})
    if body is not None:
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Leave a redirect response for the test to inspect."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def _submit(
    port: int,
    path: str,
    body: bytes,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any, bytes]:
    request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers=request_headers,
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=15) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def _open(
    port: int,
    path: str,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any, bytes]:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {}, method="GET")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=15) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def _open_server(**kwargs: Any) -> tuple[Any, threading.Thread]:
    from shadowsim.cli.serve import HTTPServer as ThreadedServer

    server = ThreadedServer(("127.0.0.1", 0), _Handler, **kwargs)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _assert_dropped(client: socket.socket, limit: float) -> None:
    client.settimeout(0.2)
    deadline = time.monotonic() + limit
    data = bytearray()
    while time.monotonic() < deadline:
        try:
            chunk = client.recv(4096)
        except TimeoutError:
            continue
        except OSError:
            return
        if chunk == b"":
            assert not bytes(data).startswith(b"HTTP/")
            return
        data += chunk
        assert not bytes(data).startswith(b"HTTP/")
    raise AssertionError(bytes(data))


def _close_server(server: Any, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_session_id_belongs_to_one_server() -> None:
    first, first_thread = _open_server()
    second, second_thread = _open_server()
    try:
        first_port = first.server_address[1]
        second_port = second.server_address[1]
        status, _headers, body = _open(first_port, "/session")
        assert status == 200
        payload = json.loads(body)
        assert isinstance(payload["id"], str)
        assert payload["id"]
        again, _headers, again_body = _open(first_port, "/session")
        assert again == 200
        assert json.loads(again_body)["id"] == payload["id"]
        _status, _headers, other = _open(second_port, "/session")
        assert json.loads(other)["id"] != payload["id"]
    finally:
        _close_server(first, first_thread)
        _close_server(second, second_thread)


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

    def hold(selection: dict[str, object], output_root: object = None) -> tuple[str, dict[str, bool]]:
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
    def fail(selection: dict[str, object], output_root: object = None) -> tuple[str, str]:
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

    def spawn(selection: dict[str, object], output_root: object = None) -> tuple[multiprocessing.Process, Any]:
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


def test_the_page_exchanges_a_query_token_for_a_cookie() -> None:
    server, thread = _open_server()
    server.token = "test-token"
    port = server.server_address[1]
    try:
        status, _headers, body = _open(port, "/")
        assert status == 401
        assert body == b"Open the URL printed when the server started.\n"

        status, headers, body = _open(port, "/?token=nope")
        assert status == 401
        assert "Set-Cookie" not in headers
        status, headers, body = _open(port, "/?token=test-token&token=test-token")
        assert status == 401
        assert "Set-Cookie" not in headers

        status, headers, body = _open(port, "/?token=wrong", {"Cookie": "shadowsim-token=test-token"})
        assert status == 401
        assert "Set-Cookie" not in headers

        status, headers, body = _open(port, "/?token=test-token")
        assert status == 303
        assert headers["Location"] == "/"
        assert headers["Set-Cookie"] == "shadowsim-token=test-token; HttpOnly; SameSite=Strict; Path=/"
        assert body == b""

        status, _headers, body = _open(port, "/", {"Cookie": "other=1; shadowsim-token=test-token"})
        assert status == 200
        assert b"ShadowSim.py Simulation Builder" in body
        status, _headers, css = _open(port, "/styles.css")
        assert status == 200
        assert b".board" in css
        status, _headers, models = _open(port, "/models")
        assert status == 200
        assert b"models" in models
    finally:
        _close_server(server, thread)


def test_post_auth_is_not_found_when_query_tokens_are_accepted() -> None:
    server, thread = _open_server()
    server.token = "test-token"
    port = server.server_address[1]
    try:
        status, _headers, _body = _submit(port, "/auth", b"token=test-token")
    finally:
        _close_server(server, thread)
    assert status == 404


def test_a_remote_server_exchanges_a_posted_token_for_a_secure_cookie() -> None:
    server, thread = _open_server()
    server.token = "test-token"
    server.accept_query_token = False
    server.tls = True
    port = server.server_address[1]
    secure = "shadowsim-token=test-token; HttpOnly; SameSite=Strict; Secure; Path=/"
    try:
        status, headers, body = _open(port, "/")
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
        assert "Set-Cookie" not in headers
        assert b'action="/auth"' in body
        assert b'type="password"' in body
        assert b"<script" not in body.lower()
        assert b"test-token" not in body

        status, headers, _body = _open(port, "/?token=test-token")
        assert status == 401
        assert "Set-Cookie" not in headers
        status, headers, _body = _open(port, "/?token=test-token", {"Cookie": "shadowsim-token=test-token"})
        assert status == 401
        assert "Set-Cookie" not in headers

        status, headers, body = _submit(port, "/auth", b"token=nope")
        assert status == 401
        assert body == b"Open the URL printed when the server started.\n"
        assert "Set-Cookie" not in headers
        status, headers, body = _submit(port, "/auth?token=test-token", b"token=nope")
        assert status == 401
        assert "Set-Cookie" not in headers

        status, _headers, body = _submit(port, "/auth", b"other=1")
        assert status == 400
        assert body == b"request body must include one token\n"
        status, _headers, body = _submit(port, "/auth", b"token=one&token=two")
        assert status == 400
        assert body == b"request body must include one token\n"
        status, _headers, body = _submit(port, "/auth", b"token=\xff")
        assert status == 400
        assert body == b"request body must include one token\n"
        status, _headers, body = _submit(port, "/auth", b"a" * (_MAX_AUTH_BODY_BYTES + 1))
        assert status == 400
        assert body == b"request body is too large\n"
        status, _headers, body = _submit(
            port,
            "/auth",
            b"token=test-token",
            {"Content-Type": "application/json"},
        )
        assert status == 415
        assert body == b"Content-Type must be application/x-www-form-urlencoded\n"

        status, headers, body = _submit(
            port,
            "/auth",
            b"token=test-token",
            {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        )
        assert status == 303
        assert headers["Location"] == "/"
        assert headers["Set-Cookie"] == secure
        assert body == b""

        status, _headers, body = _open(port, "/", {"Cookie": "shadowsim-token=test-token"})
        assert status == 200
        assert b"ShadowSim.py Simulation Builder" in body
    finally:
        _close_server(server, thread)


def test_a_posted_token_is_refused_when_the_server_has_none() -> None:
    server, thread = _open_server()
    server.accept_query_token = False
    port = server.server_address[1]
    try:
        status, headers, body = _submit(port, "/auth", b"token=test-token")
    finally:
        _close_server(server, thread)
    assert status == 401
    assert body == b"Open the URL printed when the server started.\n"
    assert "Set-Cookie" not in headers


def test_read_auth_body_rejects_a_missing_or_invalid_length() -> None:
    stream = BytesIO(b"token=test-token")
    with pytest.raises(ValueError, match="request body is required"):
        _read_auth_body({}, stream)
    with pytest.raises(ValueError, match="request body is required"):
        _read_auth_body({"Content-Length": "nope"}, stream)
    with pytest.raises(ValueError, match="request body is required"):
        _read_auth_body({"Content-Length": "-1"}, stream)
    with pytest.raises(ValueError, match="request body is required"):
        _read_auth_body({"Content-Length": ["4"]}, stream)
    assert stream.tell() == 0


def test_posted_runs_require_the_startup_token(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def run(selection: dict[str, object], output_root: object = None) -> tuple[str, dict[str, bool]]:
        calls.append("run")
        assert selection == {}
        assert output_root is None
        return ("ok", {"ok": True})

    def cancel() -> bool:
        calls.append("cancel")
        return False

    monkeypatch.setattr("shadowsim.cli.serve._run_in_child", run)
    monkeypatch.setattr("shadowsim.cli.serve._cancel_run", cancel)
    server, thread = _open_server()
    server.token = "test-token"
    port = server.server_address[1]
    bearer = {"Authorization": "Bearer test-token"}
    cookie = {"Cookie": "shadowsim-token=test-token"}
    try:
        status, body = _exchange(port, "POST", "/runs", b"{}")
        assert status == 401
        assert json.loads(body) == {"error": "unauthorized"}
        status, body = _exchange(port, "POST", "/runs/cancel")
        assert status == 401
        assert json.loads(body) == {"error": "unauthorized"}
        status, body = _exchange(port, "POST", "/runs", b"{}", {"Authorization": "Bearer nope"})
        assert status == 401
        status, body = _exchange(port, "POST", "/runs/cancel", headers={"Cookie": "shadowsim-token=nope"})
        assert status == 401
        status, body = _exchange(port, "POST", "/runs?token=test-token", b"{}")
        assert status == 401
        status, body = _exchange(port, "POST", "/runs", b"{}", {"Authorization": "Bearer caf\u00e9"})
        assert status == 401
        assert calls == []

        status, body = _exchange(port, "POST", "/runs", b"{}", bearer)
        assert status == 200
        assert json.loads(body) == {"ok": True}
        status, body = _exchange(port, "POST", "/runs", b"{}", cookie)
        assert status == 200
        status, _body = _exchange(port, "POST", "/runs/cancel", headers=bearer)
        assert status == 404
        status, _body = _exchange(port, "POST", "/runs/cancel", headers=cookie)
        assert status == 404
        assert calls == ["run", "run", "cancel", "cancel"]
    finally:
        _close_server(server, thread)


def test_post_runs_requires_json(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    def run(selection: dict[str, object], output_root: object = None) -> tuple[str, dict[str, bool]]:
        calls.append(selection)
        assert output_root is None
        return ("ok", {"ok": True})

    monkeypatch.setattr("shadowsim.cli.serve._run_in_child", run)
    server, thread = _open_server()
    port = server.server_address[1]
    plain = {"Content-Type": "text/plain"}
    try:
        status, body = _exchange(port, "POST", "/runs", b"{}", plain)
        assert status == 415
        assert json.loads(body) == {"error": "Content-Type must be application/json"}
        assert calls == []

        server.token = "test-token"
        auth = {"Authorization": "Bearer test-token"}
        status, body = _exchange(port, "POST", "/runs", b"{}", {**auth, "Content-Type": "text/plain"})
        assert status == 415
        assert json.loads(body) == {"error": "Content-Type must be application/json"}
        status, body = _exchange(
            port,
            "POST",
            "/runs",
            b"{}",
            {**auth, "Content-Type": "application/x-www-form-urlencoded"},
        )
        assert status == 415
        assert calls == []

        status, body = _exchange(
            port,
            "POST",
            "/runs",
            b"{}",
            {**auth, "Content-Type": "application/json; charset=utf-8"},
        )
        assert status == 200
        assert json.loads(body) == {"ok": True}
        status, _body = _exchange(port, "POST", "/runs/cancel", headers={**auth, "Content-Type": "text/plain"})
        assert status == 404
        assert calls == [{}]
    finally:
        _close_server(server, thread)


def test_serve_resolves_the_output_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    created: list[_QuietServer] = []

    class _RecordingQuiet(_QuietServer):
        def __init__(self, server_address: tuple[str, int], request_handler_class: type[_Handler]) -> None:
            super().__init__(server_address, request_handler_class)
            created.append(self)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("shadowsim.cli.serve.HTTPServer", _RecordingQuiet)
    assert serve("127.0.0.1", 8000, open_browser=False, output_dir="results") == 0
    resolved = (tmp_path / "results").resolve()
    assert created[0].output_root == resolved
    assert f"Saving under {resolved}" in capsys.readouterr().out


def test_a_posted_run_uses_the_output_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def run(selection: dict[str, object], output_root: object = None) -> tuple[str, dict[str, bool]]:
        seen["output_root"] = output_root
        assert selection == {}
        return ("ok", {"ok": True})

    monkeypatch.setattr("shadowsim.cli.serve._run_in_child", run)
    server, thread = _open_server()
    root = (tmp_path / "results").resolve()
    server.output_root = root
    port = server.server_address[1]
    try:
        status, body = _exchange(port, "POST", "/runs", b"{}")
    finally:
        _close_server(server, thread)
    assert status == 200
    assert json.loads(body) == {"ok": True}
    assert seen["output_root"] == root


@pytest.mark.parametrize(
    "payload",
    [b"", b"GET /session HTTP/1.1\r\nHost: 127.0.0.1\r\n"],
    ids=["silent", "partial-headers"],
)
def test_a_stalled_request_is_closed(payload: bytes) -> None:
    server, thread = _open_server(request_timeout=0.2)
    port = server.server_address[1]
    client: socket.socket | None = None
    try:
        client = socket.create_connection(("127.0.0.1", port), timeout=2)
        if payload:
            client.sendall(payload)
        _assert_dropped(client, 2)
        status, _headers, body = _open(port, "/session")
        assert status == 200
        assert isinstance(json.loads(body)["id"], str)
    finally:
        if client is not None:
            client.close()
        _close_server(server, thread)


def test_a_stalled_authenticated_body_is_closed() -> None:
    server, thread = _open_server(request_timeout=0.2)
    server.token = "test-token"
    port = server.server_address[1]
    client: socket.socket | None = None
    try:
        client = socket.create_connection(("127.0.0.1", port), timeout=2)
        client.sendall(
            b"POST /runs HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Authorization: Bearer test-token\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 100\r\n"
            b"\r\n"
            b'{"partial"'
        )
        _assert_dropped(client, 2)
        status, _headers, body = _open(port, "/session")
        assert status == 200
        assert isinstance(json.loads(body)["id"], str)
    finally:
        if client is not None:
            client.close()
        _close_server(server, thread)


def test_a_missing_token_does_not_wait_for_the_body() -> None:
    server, thread = _open_server(request_timeout=5)
    server.token = "test-token"
    port = server.server_address[1]
    client: socket.socket | None = None
    try:
        client = socket.create_connection(("127.0.0.1", port), timeout=2)
        client.settimeout(1)
        started = time.monotonic()
        client.sendall(
            b"POST /runs HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n"
        )
        data = bytearray()
        while b"unauthorized" not in data:
            chunk = client.recv(4096)
            if chunk == b"":
                break
            data += chunk
        elapsed = time.monotonic() - started
    finally:
        if client is not None:
            client.close()
        _close_server(server, thread)
    assert elapsed < 1
    assert data.startswith(b"HTTP/1.0 401")
    assert b"unauthorized" in data


def test_a_full_handler_cap_closes_the_next_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    release = threading.Event()

    def hold(selection: dict[str, object], output_root: object = None) -> tuple[str, dict[str, bool]]:
        started.set()
        assert release.wait(timeout=5)
        return ("ok", {"ok": True})

    monkeypatch.setattr("shadowsim.cli.serve._run_in_child", hold)
    server, thread = _open_server(max_handlers=1)
    port = server.server_address[1]
    outcome: dict[str, tuple[int, bytes]] = {}
    extra: socket.socket | None = None

    def post_run() -> None:
        outcome["result"] = _exchange(port, "POST", "/runs", b"{}")

    poster = threading.Thread(target=post_run)
    poster.start()
    try:
        assert started.wait(timeout=2)
        extra = socket.create_connection(("127.0.0.1", port), timeout=2)
        try:
            extra.sendall(b"GET /session HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        except OSError:
            pass
        _assert_dropped(extra, 2)
        release.set()
        poster.join(timeout=5)
        assert outcome["result"] == (200, b'{"ok": true}')
        status, _headers, body = _open(port, "/session")
        assert status == 200
        assert isinstance(json.loads(body)["id"], str)
    finally:
        release.set()
        poster.join(timeout=5)
        if extra is not None:
            extra.close()
        _close_server(server, thread)


def test_a_long_run_is_not_cut_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from shadowsim.cli import serve as serve_cli

    seen: dict[str, Any] = {}
    end_read_timeout = serve_cli._end_read_timeout

    def spy(handler: Any) -> None:
        end_read_timeout(handler)
        seen["handler"] = handler

    def hold(selection: dict[str, object], output_root: object = None) -> tuple[str, dict[str, bool]]:
        seen["timeout"] = seen["handler"].connection.gettimeout()
        time.sleep(0.5)
        return ("ok", {"ok": True})

    monkeypatch.setattr(serve_cli, "_end_read_timeout", spy)
    monkeypatch.setattr(serve_cli, "_run_in_child", hold)
    server, thread = _open_server(request_timeout=0.2)
    port = server.server_address[1]
    try:
        status, body = _exchange(port, "POST", "/runs", b"{}")
    finally:
        _close_server(server, thread)
    assert status == 200
    assert json.loads(body) == {"ok": True}
    assert seen["timeout"] is None


def test_a_handler_that_fails_to_start_releases_its_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    from shadowsim.cli.serve import HTTPServer as ThreadedServer

    def boom(self: object, request: object, client_address: object) -> None:
        raise RuntimeError("start failed")

    monkeypatch.setattr("shadowsim.cli.serve.ThreadingMixIn.process_request", boom)
    server = ThreadedServer(("127.0.0.1", 0), _Handler, max_handlers=1)
    try:
        with pytest.raises(RuntimeError, match="start failed"):
            server.process_request(object(), ("127.0.0.1", 9))
        assert server._handler_slots.acquire(blocking=False)
        server._handler_slots.release()
    finally:
        server.server_close()
