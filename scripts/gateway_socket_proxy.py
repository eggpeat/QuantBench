#!/usr/bin/env python3
"""Exact-model HTTP bridge for the credential-bearing auth gateway."""
from __future__ import annotations

import argparse
import json
import os
import signal
import select
import socket
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_MODEL_SELECTOR = "openai-codex/gpt-5.6-sol:max"
MODEL_THINKING_SUFFIXES = frozenset(
    {"minimal", "low", "medium", "high", "xhigh", "max", "none", "off", "auto", "raw"}
)
MAX_HEADER_BYTES = 64 * 1024
MAX_BODY_BYTES = 16 * 1024 * 1024


def _selector_aliases(selector: str) -> tuple[str, str, set[str]]:
    if not isinstance(selector, str) or not selector or any(char.isspace() for char in selector):
        raise ValueError("allowed model selector must be a non-empty string without whitespace")
    provider, sep, model = selector.partition("/")
    if not sep or not provider or not model:
        raise ValueError(f"allowed model selector must be provider/model[:thinking], got {selector!r}")
    model_parts = model.rsplit(":", 1)
    base_model = model_parts[0] if len(model_parts) == 2 and model_parts[1] in MODEL_THINKING_SUFFIXES else model
    if not base_model or ":" in base_model:
        raise ValueError(f"allowed model selector has malformed model id: {selector!r}")
    base = f"{provider}/{base_model}"
    return provider, base_model, {selector, base, base_model}


def authorize_http_model_request(
    method: str,
    target: str,
    body: bytes,
    allowed_model_selector: str,
) -> tuple[str, str]:
    """Authorize one parsed HTTP request before it reaches the host gateway."""
    provider, model_id, accepted_models = _selector_aliases(allowed_model_selector)
    path = urlparse(target).path
    if method.upper() == "GET":
        if path in {"/models", "/v1/models"}:
            return "listing", ""
        return "deny", "unsupported GET endpoint"
    if method.upper() not in {"POST", "PUT", "PATCH"}:
        return "deny", "unsupported HTTP method"
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "deny", "request body is not valid JSON"
    if not isinstance(payload, dict) or not isinstance(payload.get("model"), str):
        return "deny", "request body has no inspectable model selector"
    if payload["model"] not in accepted_models:
        return "deny", f"model selector {payload['model']!r} is not allowed"
    return "allow", ""


def _read_http_request(incoming: socket.socket, allowed_model_selector: str) -> tuple[str, bytes]:
    """Read and authorize one HTTP/1 request, retaining every original byte."""
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = incoming.recv(65536)
        if not chunk:
            raise ValueError("connection closed before complete HTTP headers")
        data.extend(chunk)
        if len(data) > MAX_HEADER_BYTES:
            raise ValueError("HTTP headers exceed proxy limit")
    header_end = data.index(b"\r\n\r\n") + 4
    header_bytes = bytes(data[:header_end])
    header_lines = header_bytes[:-4].split(b"\r\n")
    try:
        method, target, version = header_lines[0].decode("latin-1").split(" ", 2)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("malformed HTTP request line") from exc
    if version not in {"HTTP/1.0", "HTTP/1.1"}:
        raise ValueError("unsupported HTTP version")
    headers: dict[str, str] = {}
    for raw_header in header_lines[1:]:
        try:
            name, value = raw_header.decode("latin-1").split(":", 1)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("malformed HTTP header") from exc
        name = name.strip().lower()
        if not name or name in headers:
            raise ValueError("duplicate or empty HTTP header")
        headers[name] = value.strip()
    if "expect" in headers:
        raise ValueError("Expect requests are not inspectable")
    transfer_encoding = headers.get("transfer-encoding")
    if transfer_encoding:
        raise ValueError("Transfer-Encoding request bodies are not inspectable")
    raw_length = headers.get("content-length", "0")
    if not raw_length or any(char not in "0123456789" for char in raw_length):
        raise ValueError("invalid Content-Length")
    content_length = int(raw_length, 10)
    if content_length < 0 or content_length > MAX_BODY_BYTES:
        raise ValueError("request body exceeds proxy limit")
    while len(data) - header_end < content_length:
        chunk = incoming.recv(min(65536, header_end + content_length - len(data)))
        if not chunk:
            raise ValueError("connection closed before complete HTTP body")
        data.extend(chunk)
    body = bytes(data[header_end : header_end + content_length])
    decision, reason = authorize_http_model_request(method, target, body, allowed_model_selector)
    if decision == "deny":
        raise PermissionError(reason)
    return decision, bytes(data[: header_end + content_length])


def _json_response(status: int, payload: object) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    phrase = {200: "OK", 400: "Bad Request", 403: "Forbidden"}.get(status, "Error")
    return (
        f"HTTP/1.1 {status} {phrase}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii") + body


def _model_listing_response(allowed_model_selector: str) -> bytes:
    provider, model_id, _ = _selector_aliases(allowed_model_selector)
    return _json_response(
        200,
        {
            "object": "list",
            "data": [{"id": model_id, "object": "model", "owned_by": provider}],
        },
    )

def _connection_close_request(request: bytes) -> bytes:
    """Make the single authorized HTTP exchange self-terminating upstream."""
    header_end = request.index(b"\r\n\r\n")
    headers = request[:header_end].split(b"\r\n")
    connection_headers = [
        header for header in headers[1:] if header.lower().startswith(b"connection:")
    ]
    if len(connection_headers) == 1 and connection_headers[0].split(b":", 1)[1].strip().lower() == b"close":
        return request
    filtered = [
        header for header in headers[1:] if not header.lower().startswith(b"connection:")
    ]
    return b"\r\n".join([headers[0], *filtered, b"Connection: close"]) + b"\r\n\r\n" + request[header_end + 4 :]


def _serve_connection(
    incoming: socket.socket,
    outgoing: socket.socket,
    allowed_model_selector: str,
) -> None:
    try:
        decision, request = _read_http_request(incoming, allowed_model_selector)
        if decision == "listing":
            incoming.sendall(_model_listing_response(allowed_model_selector))
            return
        outgoing.sendall(_connection_close_request(request))
        _relay_response(outgoing, incoming)
    except PermissionError as exc:
        try:
            incoming.sendall(_json_response(403, {"error": {"message": str(exc), "type": "model_not_allowed"}}))
        except OSError:
            pass
    except (OSError, ValueError) as exc:
        try:
            incoming.sendall(_json_response(400, {"error": {"message": str(exc), "type": "invalid_request"}}))
        except OSError:
            pass
    finally:
        for conn in (incoming, outgoing):
            try:
                conn.close()
            except OSError:
                pass


def _relay_response(source: socket.socket, destination: socket.socket) -> None:
    """Relay a response while propagating a downstream disconnect upstream."""
    while True:
        readable, _, _ = select.select([source, destination], [], [])
        if destination in readable:
            # Any bytes after the one authorized Content-Length request are
            # outside this single-exchange bridge. Drain them so EOF remains
            # observable instead of disabling cancellation monitoring.
            try:
                downstream = destination.recv(65536)
            except OSError:
                return
            if not downstream:
                return
        if source not in readable:
            continue
        try:
            chunk = source.recv(65536)
        except OSError:
            return
        if not chunk:
            return
        destination.sendall(chunk)


def _loopback_target(target: str) -> tuple[str, int]:
    parsed = urlparse(target)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("target must be an http://127.0.0.1 or localhost URL")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("target must be a bare loopback origin")
    if parsed.port is None:
        raise ValueError("target must include a port")
    return parsed.hostname, parsed.port


def serve_unix(
    socket_path: Path,
    target: str,
    allowed_model_selector: str = DEFAULT_MODEL_SELECTOR,
) -> int:
    _selector_aliases(allowed_model_selector)
    host, port = _loopback_target(target)
    socket_path = socket_path.expanduser().resolve()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        socket_path.unlink()
    except FileNotFoundError:
        pass
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(64)
    listener.settimeout(0.5)
    stopping = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopping.set()
        try:
            listener.close()
        except OSError:
            pass

    old_term = signal.signal(signal.SIGTERM, stop)
    old_int = signal.signal(signal.SIGINT, stop)
    workers: list[threading.Thread] = []
    try:
        while not stopping.is_set():
            try:
                incoming, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if stopping.is_set():
                    break
                raise
            try:
                outgoing = socket.create_connection((host, port), timeout=5)
            except OSError:
                incoming.close()
                continue
            worker = threading.Thread(
                target=_serve_connection,
                args=(incoming, outgoing, allowed_model_selector),
                daemon=True,
            )
            workers.append(worker)
            worker.start()
    finally:
        stopping.set()
        try:
            listener.close()
        except OSError:
            pass
        for worker in workers:
            worker.join(timeout=1)
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
    return 0


def run_tcp(
    socket_path: Path,
    listen: str,
    command: list[str],
    allowed_model_selector: str = DEFAULT_MODEL_SELECTOR,
) -> int:
    if not command:
        raise ValueError("run-tcp requires a command after --")
    _selector_aliases(allowed_model_selector)
    host, sep, raw_port = listen.rpartition(":")
    if not sep or host not in {"127.0.0.1", "localhost"}:
        raise ValueError("listen must be 127.0.0.1:PORT")
    port = int(raw_port)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, port))
    listener.listen(64)
    listener.settimeout(0.5)
    stopping = threading.Event()
    workers: list[threading.Thread] = []

    child = subprocess.Popen(command, start_new_session=True)

    def stop(signum: int, _frame: object) -> None:
        stopping.set()
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass
        try:
            listener.close()
        except OSError:
            pass

    old_term = signal.signal(signal.SIGTERM, stop)
    old_int = signal.signal(signal.SIGINT, stop)
    try:
        while child.poll() is None and not stopping.is_set():
            try:
                incoming, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if stopping.is_set():
                    break
                raise
            try:
                outgoing = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                outgoing.connect(str(socket_path.expanduser().resolve()))
            except OSError:
                incoming.close()
                continue
            worker = threading.Thread(
                target=_serve_connection,
                args=(incoming, outgoing, allowed_model_selector),
                daemon=True,
            )
            workers.append(worker)
            worker.start()
        if stopping.is_set() and child.poll() is None:
            child.wait(timeout=10)
        return int(child.wait())
    finally:
        stopping.set()
        try:
            listener.close()
        except OSError:
            pass
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        for worker in workers:
            worker.join(timeout=1)
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    serve = sub.add_parser("serve-unix")
    serve.add_argument("--socket", required=True, type=Path)
    serve.add_argument("--target", required=True)
    serve.add_argument("--model-selector", default=DEFAULT_MODEL_SELECTOR)
    tcp = sub.add_parser("run-tcp")
    tcp.add_argument("--socket", required=True, type=Path)
    tcp.add_argument("--listen", required=True)
    tcp.add_argument("--model-selector", default=DEFAULT_MODEL_SELECTOR)
    tcp.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.mode == "serve-unix":
            return serve_unix(args.socket, args.target, args.model_selector)
        command = list(args.command)
        if command and command[0] == "--":
            command = command[1:]
        return run_tcp(args.socket, args.listen, command, args.model_selector)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
