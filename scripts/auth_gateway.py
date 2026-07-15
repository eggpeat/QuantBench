#!/usr/bin/env python3
"""Start and verify the host-side OMP auth gateway for Quant Bench runs."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = PROJECT_ROOT / "artifacts"
AUTH_ARTIFACT_ROOT = ARTIFACT_ROOT / "auth-gateway"
DEFAULT_HOST_AGENT_DIR = Path.home() / ".omp" / "agent"
SAFE_CHILD_ENV_KEYS = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "PI_CODING_AGENT_DIR",
)
AUTH_GATEWAY_PROVIDER_ENV_KEYS = (
    "ALIBABA_CODING_PLAN_API_KEY",
    "ALIBABA_TOKEN_PLAN_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "FIREWORKS_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
    "GMI_API_KEY",
    "KIMI_API_KEY",
    "KIMI_CODE_API_KEY",
    "LIGHTNING_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_CODE_API_KEY",
    "MINIMAX_CODE_PLAN_KEY",
    "MINIMAX_CODING_API_KEY",
    "MOONSHOT_API_KEY",
    "NVIDIA_API_KEY",
    "OPENAI_API_KEY",
    "WAFER_PASS_API_KEY",
    "WAFER_SERVERLESS_API_KEY",
    "XAI_API_KEY",
    "XAI_OAUTH_TOKEN",
    "XIAOMI_API_KEY",
    "ZAI_API_KEY",
    "ZHIPUAI_API_KEY",
)

DEFAULT_MODEL_SELECTOR = "openai-codex/gpt-5.6-sol:max"

def host_agent_dir() -> Path:
    configured = os.environ.get("PI_CODING_AGENT_DIR")
    return Path(configured).expanduser() if configured else DEFAULT_HOST_AGENT_DIR


def leading_spaces(value: str) -> int:
    return len(value) - len(value.lstrip(" "))


CREDENTIAL_CONFIG_KEYS = {
    "auth",
    "authorization",
    "accesskey",
    "accesskeyid",
    "apisecret",
    "credential",
    "credentials",
    "password",
    "privatekey",
    "secret",
    "secretkey",
    "token",
    "xapikey",
}
CREDENTIAL_CONFIG_SUFFIXES = (
    "accesstoken",
    "apikey",
    "apitoken",
    "authtoken",
    "bearertoken",
    "clientsecret",
    "credentialfile",
    "privatekey",
    "secret",
    "secretkey",
    "idtoken",
    "refreshtoken",
)


def normalized_config_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def is_env_reference(value: str) -> bool:
    value = unquote_env_value(value)
    for key in AUTH_GATEWAY_PROVIDER_ENV_KEYS:
        if value == key or value == f"${key}" or value == f"${{{key}}}":
            return True
        if value == f"Bearer ${key}" or value == f"Bearer ${{{key}}}":
            return True
    return False

def is_safe_auth_value(value: str) -> bool:
    return normalized_config_key(unquote_env_value(value)) in {
        "none",
        "oauth",
        "oauth2",
        "apikey",
        "bearer",
    }



def is_credential_config_key(key: str) -> bool:
    return key in CREDENTIAL_CONFIG_KEYS or any(key.endswith(suffix) for suffix in CREDENTIAL_CONFIG_SUFFIXES)



def is_safe_wafer_command(value: str) -> bool:
    unquoted = unquote_env_value(value).strip()
    if not unquoted.startswith("!"):
        return False
    try:
        parts = shlex.split(unquoted[1:].strip())
    except ValueError:
        return False
    if len(parts) != 3 or parts[0] != "python3" or parts[2] != "wafer":
        return False
    script = parts[1]
    return Path(script).name == "omp-api-key.py" and not re.search(r"[\s;&|`$<>]", script)


def has_credential_value(value: str) -> bool:
    value = unquote_env_value(value).lower()
    return bool(
        re.search(r"://[^/\s:@]+:[^/\s@]+@", value)
        or re.search(
            r"[?&](?:api[-_]?key|access[-_]?token|auth[-_]?token|bearer[-_]?token|refresh[-_]?token|client[-_]?secret|secret|token|key)=",
            value,
        )
    )


def has_inline_credential_mapping(value: str) -> bool:
    for match in re.finditer(r"(?:[{,]\s*)[\"']?([A-Za-z0-9_-]+)[\"']?\s*:", value):
        if is_credential_config_key(normalized_config_key(match.group(1))):
            return True
    return False


def safe_header_block(source_lines: list[str], start_idx: int) -> tuple[list[str], int]:
    header_line = source_lines[start_idx]
    header_indent = leading_spaces(header_line)
    kept: list[str] = []
    idx = start_idx + 1
    skip_indent: int | None = None
    while idx < len(source_lines):
        line = source_lines[idx]
        stripped = line.strip()
        indent = leading_spaces(line)
        if stripped and indent <= header_indent:
            break
        if skip_indent is not None:
            if not stripped:
                idx += 1
                continue
            if indent > skip_indent:
                idx += 1
                continue
            skip_indent = None
        if not stripped:
            idx += 1
            continue
        _key_name, sep, value = stripped.partition(":")
        if sep and is_env_reference(value):
            kept.append(line)
        else:
            skip_indent = indent
        idx += 1
    return ([header_line, *kept] if kept else []), idx


def safe_gateway_models_yml(text: str) -> str:
    source_lines = text.splitlines()
    lines: list[str] = []
    skip_indent: int | None = None
    idx = 0
    while idx < len(source_lines):
        line = source_lines[idx]
        stripped = line.strip()
        indent = leading_spaces(line)
        if skip_indent is not None:
            if not stripped:
                idx += 1
                continue
            if indent > skip_indent:
                idx += 1
                continue
            skip_indent = None
        lowered = stripped.lower()
        if lowered.startswith("headers:"):
            kept_headers, idx = safe_header_block(source_lines, idx)
            lines.extend(kept_headers)
            continue
        if has_inline_credential_mapping(stripped):
            skip_indent = indent
            idx += 1
            continue
        key_name, sep, value = stripped.partition(":")
        if sep:
            normalized_key = normalized_config_key(key_name)
            is_wafer_cmd = normalized_key == "apikey" and is_safe_wafer_command(value)
            if not is_wafer_cmd and has_credential_value(value):
                skip_indent = indent
                idx += 1
                continue
            if (
                is_credential_config_key(normalized_key)
                and not is_env_reference(value)
                and not (normalized_key == "auth" and is_safe_auth_value(value))
                and not is_wafer_cmd
            ):
                skip_indent = indent
                idx += 1
                continue
        lines.append(line)
        idx += 1
    return "\n".join(lines).rstrip() + "\n"


def prepare_gateway_agent_dir(agent_dir: Path, source_agent_dir: Path | None = None) -> None:
    agent_dir.mkdir(parents=True, exist_ok=True)
    source_models = (source_agent_dir or host_agent_dir()) / "models.yml"
    if source_models.exists():
        content = safe_gateway_models_yml(source_models.read_text(encoding="utf-8"))
    else:
        content = "providers:\n"
    (agent_dir / "models.yml").write_text(content, encoding="utf-8")



def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def path_slug(value: str) -> str:
    value = value.replace("..", "-")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._").lower()
    value = re.sub(r"-+", "-", value)
    return value or "run"

def minimal_child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: os.environ[key] for key in SAFE_CHILD_ENV_KEYS if key in os.environ}
    env.setdefault("PI_CODING_AGENT_DIR", str(Path.home() / ".omp" / "agent"))
    env.update(extra or {})
    return env


def unquote_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def selected_provider_env_from_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    selected: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in AUTH_GATEWAY_PROVIDER_ENV_KEYS:
            selected[key] = unquote_env_value(value)
    return selected


def selected_provider_env(source_agent_dir: Path | None = None) -> dict[str, str]:
    selected = selected_provider_env_from_file((source_agent_dir or host_agent_dir()) / ".env")
    for key in AUTH_GATEWAY_PROVIDER_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            selected[key] = value
    return selected


def auth_broker_child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    return minimal_child_env({**selected_provider_env(), **(extra or {})})


def auth_gateway_child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    return minimal_child_env({**selected_provider_env(), **(extra or {})})


def free_loopback_bind() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return f"127.0.0.1:{sock.getsockname()[1]}"


def require_loopback_bind(bind: str, label: str) -> str:
    host, sep, port = bind.rpartition(":")
    if not sep or not host or not port:
        raise ValueError(f"{label} must be host:port or auto")
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError(f"{label} must bind to 127.0.0.1 or localhost")
    return bind


def read_json_url(url: str, timeout: float = 2.0) -> tuple[int, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body) if body else None


def wait_json(url: str, *, timeout_sec: float = 10.0) -> tuple[int, Any]:
    deadline = time.monotonic() + timeout_sec
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            return read_json_url(url)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {url}: {last_error}")
def _bounded_reason(value: object, limit: int = 240) -> str:
    text = " ".join(str(value).split())
    return text[:limit]


def wait_for_unix_socket(
    process: subprocess.Popen[str],
    socket_path: Path,
    *,
    timeout_sec: float = 5.0,
) -> tuple[bool, str]:
    """Wait for a proxy socket while treating an early process exit as failure."""
    deadline = time.monotonic() + max(0.0, timeout_sec)
    while True:
        if socket_path.exists():
            returncode = process.poll()
            if returncode is None:
                return True, "socket created"
            return False, _bounded_reason(f"socket proxy exited before readiness (code {returncode})")
        returncode = process.poll()
        if returncode is not None:
            return False, _bounded_reason(f"socket proxy exited before creating socket (code {returncode})")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.05, remaining))
    if socket_path.exists():
        returncode = process.poll()
        if returncode is None:
            return True, "socket created"
        return False, _bounded_reason(f"socket proxy exited before readiness (code {returncode})")
    return False, _bounded_reason(f"timed out waiting for UNIX socket after {max(0.0, timeout_sec):.1f}s")


def count_models(payload: Any) -> int | None:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("models", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return None


def omp_cli_command(*args: str) -> list[str]:
    bun = Path.home() / ".bun" / "bin" / "bun"
    cli = (
        Path.home()
        / ".bun"
        / "install"
        / "global"
        / "node_modules"
        / "@oh-my-pi"
        / "pi-coding-agent"
        / "dist"
        / "cli.js"
    )
    prefix = [str(bun), str(cli)] if bun.is_file() and cli.is_file() else ["omp"]
    return [*prefix, *args]


def broker_token() -> str:
    proc = subprocess.run(omp_cli_command("auth-broker", "token", "--json"), text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        raise RuntimeError(f"auth-broker token failed: {proc.stderr.strip() or proc.stdout.strip()}")
    parsed = json.loads(proc.stdout)
    token = parsed.get("token") if isinstance(parsed, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("auth-broker token output did not include token")
    return token


def spawn(cmd: list[str], *, log_path: Path, env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("a", encoding="utf-8")
    return subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env if env is not None else minimal_child_env(),
        text=True,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def stop_process(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


GATEWAY_SOCKET_PROXY = PROJECT_ROOT / "scripts" / "gateway_socket_proxy.py"


def _read_pid_cmdline(pid: int) -> list[str] | None:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, OSError):
        return None
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def _command_matches(recorded: list[str], actual: list[str] | None) -> bool:
    if not actual or not recorded:
        return False
    if actual == recorded:
        return True
    if Path(actual[0]).name != Path(recorded[0]).name and Path(actual[0]).name not in {Path(recorded[0]).name, "python", "python3"}:
        return False
    return all(item in actual for item in recorded[1:])


def _pid_verified(pid: int, command: list[str]) -> bool:
    return _command_matches(command, _read_pid_cmdline(pid))


def _generation_number(out_dir: Path) -> int:
    generations = [int(path.name.split("-", 1)[1]) for path in out_dir.glob("generation-*") if path.name.split("-", 1)[1].isdigit()]
    return max(generations, default=0)


def _live_generation_pids(status: dict[str, Any]) -> list[int]:
    live: list[int] = []
    for name in ("broker", "gateway", "socket_proxy"):
        pid = status.get(f"{name}_pid")
        command = status.get(f"{name}_cmd")
        if isinstance(pid, int) and isinstance(command, list) and _pid_verified(pid, [str(item) for item in command]):
            live.append(pid)
    return live


def _stop_recorded_pid(pid: int, command: list[str]) -> bool:
    if not _pid_verified(pid, command):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _read_pid_cmdline(pid) is None:
            return True
        time.sleep(0.1)
    if _pid_verified(pid, command):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
    return _read_pid_cmdline(pid) is None


def _write_status(path: Path, status: dict[str, Any]) -> None:
    path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stop_run(run_id: str) -> tuple[int, dict[str, Any]]:
    run_id = path_slug(run_id)
    out_dir = AUTH_ARTIFACT_ROOT / run_id
    status_path = out_dir / "status.json"
    if not status_path.exists():
        return 1, {"run_id": run_id, "passed": False, "error": "run ID has no status"}
    status = json.loads(status_path.read_text(encoding="utf-8"))
    generation_dir = Path(status.get("generation_dir", out_dir))
    generation_status_path = generation_dir / "status.json"
    generation_status = (
        json.loads(generation_status_path.read_text(encoding="utf-8"))
        if generation_status_path.exists()
        else dict(status)
    )
    for name in ("broker", "gateway", "socket_proxy"):
        pid = generation_status.get(f"{name}_pid")
        command = generation_status.get(f"{name}_cmd")
        if isinstance(pid, int) and isinstance(command, list):
            _stop_recorded_pid(pid, [str(item) for item in command])
    generation_status.update({"run_state": "stopped", "stopped": True, "keep_running": False})
    _write_status(generation_status_path, generation_status)
    status.update(generation_status)
    status["generation_dir"] = str(generation_dir)
    _write_status(status_path, status)
    return 0, status
def _restart_error(prior: dict[str, Any]) -> str | None:
    if _live_generation_pids(prior):
        return "verified live generation refuses restart"
    if prior.get("run_state") != "stopped" or prior.get("stopped") is not True:
        return "prior generation must be explicitly stopped before restart"
    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker-bind", default="auto", help="host:port or auto for a free loopback port.")
    parser.add_argument("--gateway-bind", default="auto", help="host:port or auto for a free loopback port.")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--unix-socket", type=Path, default=None)
    modes = parser.add_mutually_exclusive_group()
    parser.add_argument(
        "--model-selector",
        default=DEFAULT_MODEL_SELECTOR,
        help="Exact evaluated selector allowed through the optional UNIX-socket proxy.",
    )
    modes.add_argument("--keep-running", action="store_true", help="Leave broker/gateway/proxy running.")
    modes.add_argument("--stop-run", metavar="RUN_ID", help="Safely stop a recorded gateway generation.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.stop_run:
        code, status = stop_run(args.stop_run)
        print(json.dumps(status, indent=2, sort_keys=True))
        return code
    if args.unix_socket is not None:
        args.unix_socket = args.unix_socket.expanduser().resolve()
    run_id = path_slug(args.run_id or f"smoke-{now_stamp()}")
    out_dir = AUTH_ARTIFACT_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    prior_path = out_dir / "status.json"
    if prior_path.exists():
        try:
            prior = json.loads(prior_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prior = {}
        error = _restart_error(prior)
        if error:
            status = {"run_id": run_id, "passed": False, "error": error}
            print(json.dumps(status, indent=2, sort_keys=True))
            return 1
    generation = _generation_number(out_dir) + 1
    generation_dir = out_dir / f"generation-{generation}"
    generation_dir.mkdir(parents=True, exist_ok=True)
    try:
        broker_bind = free_loopback_bind() if args.broker_bind == "auto" else require_loopback_bind(args.broker_bind, "--broker-bind")
        gateway_bind = free_loopback_bind() if args.gateway_bind == "auto" else require_loopback_bind(args.gateway_bind, "--gateway-bind")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    broker_url = f"http://{broker_bind}"
    gateway_url = f"http://{gateway_bind}"
    broker: subprocess.Popen[str] | None = None
    gateway: subprocess.Popen[str] | None = None
    socket_proxy: subprocess.Popen[str] | None = None
    status: dict[str, Any] = {
        "run_id": run_id,
        "generation": generation,
        "generation_dir": str(generation_dir),
        "broker_url": broker_url,
        "gateway_url": gateway_url,
        "keep_running": bool(args.keep_running),
        "run_state": "starting",
        "token_redacted": True,
        "model_selector": args.model_selector,
    }
    try:
        broker_cmd = omp_cli_command("auth-broker", "serve", "--bind", broker_bind)
        broker = spawn(broker_cmd, log_path=generation_dir / "broker.log", env=auth_broker_child_env())
        status.update({"broker_pid": broker.pid, "broker_cmd": broker_cmd})
        code, health = wait_json(f"{broker_url}/v1/healthz")
        status["broker_health_status"] = code
        status["broker_health"] = health
        token = broker_token()
        gateway_agent_dir = generation_dir / "gateway-agent"
        prepare_gateway_agent_dir(gateway_agent_dir)
        env = auth_gateway_child_env({"OMP_AUTH_BROKER_URL": broker_url, "OMP_AUTH_BROKER_TOKEN": token, "PI_CODING_AGENT_DIR": str(gateway_agent_dir)})
        gateway_cmd = omp_cli_command("auth-gateway", "serve", "--bind", gateway_bind, "--no-auth")
        gateway = spawn(gateway_cmd, log_path=generation_dir / "gateway.log", env=env)
        status.update({"gateway_pid": gateway.pid, "gateway_cmd": gateway_cmd})
        code, health = wait_json(f"{gateway_url}/healthz")
        status["gateway_health_status"] = code
        status["gateway_agent_dir"] = str(gateway_agent_dir)
        status["gateway_health"] = health
        code, models = wait_json(f"{gateway_url}/v1/models")
        status["models_status"] = code
        status["models_count"] = count_models(models)
        if args.unix_socket:
            proxy_cmd = [
                sys.executable,
                str(GATEWAY_SOCKET_PROXY),
                "serve-unix",
                "--socket",
                str(args.unix_socket),
                "--target",
                gateway_url,
                "--model-selector",
                args.model_selector,
            ]
            try:
                args.unix_socket.unlink()
            except FileNotFoundError:
                pass
            socket_proxy = spawn(proxy_cmd, log_path=generation_dir / "socket-proxy.log", env=minimal_child_env())
            status.update({"socket_proxy_pid": socket_proxy.pid, "socket_proxy_cmd": proxy_cmd, "gateway_socket": str(args.unix_socket)})
            ready, reason = wait_for_unix_socket(socket_proxy, args.unix_socket)
            status["socket_proxy_ready"] = ready
            status["socket_proxy_reason"] = reason
            if not ready:
                raise RuntimeError(reason)
        status["passed"] = status["broker_health_status"] == 200 and status["gateway_health_status"] == 200 and status["models_status"] == 200 and isinstance(status["models_count"], int) and status["models_count"] > 0 and status.get("socket_proxy_ready", True)
        status["run_state"] = "running" if args.keep_running and status["passed"] else "stopped"
        return 0 if status["passed"] else 1
    except Exception as exc:
        status.update({"passed": False, "run_state": "stopped", "error": _bounded_reason(exc)})
        return 1
    finally:
        if not args.keep_running or not status.get("passed"):
            stop_process(socket_proxy)
            stop_process(gateway)
            stop_process(broker)
            if args.unix_socket:
                try:
                    args.unix_socket.unlink()
                except OSError:
                    pass
            status["stopped"] = True
            status["run_state"] = "stopped"
        _write_status(generation_dir / "status.json", status)
        _write_status(out_dir / "status.json", status)
        print(json.dumps(status, indent=2, sort_keys=True))

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
