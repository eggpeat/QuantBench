#!/usr/bin/env python3
"""Run a command inside the OMP model evaluation bubblewrap sandbox."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]

def resolve_host_agent_dir() -> Path:
    configured = os.environ.get("OMP_AGENT_DIR")
    return Path(configured).expanduser().resolve() if configured else (Path.home() / ".omp" / "agent").resolve()


def resolve_host_bun_dir() -> Path:
    configured = os.environ.get("BUN_INSTALL")
    if configured:
        return Path(configured).expanduser().resolve()
    bun = shutil.which("bun")
    if bun:
        return Path(bun).resolve().parent.parent
    return (Path.home() / ".bun").resolve()


HOST_AGENT_DIR = resolve_host_agent_dir()
HOST_BUN_DIR = resolve_host_bun_dir()
SANDBOX_RUNTIME_DIR = Path("/opt/omp-runtime")
SANDBOX_HOME = Path("/home/agent")
SANDBOX_AGENT_DIR = SANDBOX_HOME / ".omp" / "agent"
SANDBOX_WORKSPACE = Path("/workspace")
SANDBOX_MODEL_REF = "openai-codex/gpt-5.6-sol:max"
MODEL_THINKING_SUFFIXES = frozenset(
    {"minimal", "low", "medium", "high", "xhigh", "max", "none", "off", "auto", "raw"}
)


def model_ref_parts(model_ref: str) -> tuple[str, str]:
    """Return provider and bare model id for one fully-qualified selector."""
    if not isinstance(model_ref, str) or not model_ref or any(char.isspace() for char in model_ref):
        raise ValueError("model selector must be a non-empty string without whitespace")
    base = model_ref
    provider, sep, model_id = base.partition("/")
    if not sep or not provider or not model_id:
        raise ValueError(f"model selector must be provider/model[:thinking], got {model_ref!r}")
    maybe_suffix = model_id.rsplit(":", 1)
    if len(maybe_suffix) == 2 and maybe_suffix[1] in MODEL_THINKING_SUFFIXES:
        model_id = maybe_suffix[0]
    if not model_id or ":" in model_id:
        raise ValueError(f"model selector has malformed model id: {model_ref!r}")
    return provider, model_id


def model_selector_from_command(command: list[str], *, required: bool) -> str:
    """Extract exactly one OMP --model selector from a command line."""
    selectors: list[str] = []
    idx = 0
    while idx < len(command):
        arg = command[idx]
        if arg == "--model":
            if idx + 1 >= len(command) or not command[idx + 1]:
                raise ValueError("--model requires an exact selector")
            selectors.append(command[idx + 1])
            idx += 2
            continue
        if arg.startswith("--model="):
            value = arg.partition("=")[2]
            if not value:
                raise ValueError("--model requires an exact selector")
            selectors.append(value)
        idx += 1
    if not selectors:
        if required:
            raise ValueError("sandbox gateway runs require an exact --model selector")
        return SANDBOX_MODEL_REF
    if len(selectors) != 1:
        raise ValueError("sandbox command must contain exactly one --model selector")
    model_ref_parts(selectors[0])
    return selectors[0]
SAFE_MODEL_KEYS = {
    "api",
    "compat",
    "contextWindow",
    "id",
    "input",
    "maxTokens",
    "name",
    "output",
    "reasoning",
    "thinking",
}
SAFE_COMPAT_KEYS = {
    "maxTokensField",
    "reasoningContentField",
    "supportsDeveloperRole",
    "supportsMultipleSystemMessages",
    "supportsReasoningEffort",
    "reasoningEffortMap",
    "supportsStore",
    "thinkingFormat",
}


def require_path(path: Path, label: str) -> Path:
    if not path.exists():
        raise SystemExit(f"{label} does not exist: {path}")
    return path.resolve()


def copy_tree_contents(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for child in sorted(src.iterdir()):
        target = dst / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def copy_model_cache(
    src_agent_dir: Path,
    dst_agent_dir: Path,
    allowed_providers: set[str] | None = None,
    allowed_model_ref: str | None = None,
) -> bool:
    source = src_agent_dir / "models.db"
    if not source.exists():
        return False
    target = dst_agent_dir / "models.db"
    dst_agent_dir.mkdir(parents=True, exist_ok=True)
    selected_provider: str | None = None
    selected_model_id: str | None = None
    if allowed_model_ref is not None:
        selected_provider, selected_model_id = model_ref_parts(allowed_model_ref)
        allowed_providers = set(allowed_providers or {selected_provider})
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src:
            with sqlite3.connect(target) as dst:
                src.backup(dst)
                if allowed_providers is not None:
                    if allowed_providers:
                        placeholders = ",".join("?" for _ in allowed_providers)
                        dst.execute(
                            f"delete from model_cache where provider_id not in ({placeholders})",
                            tuple(sorted(allowed_providers)),
                        )
                    else:
                        dst.execute("delete from model_cache")
                if selected_provider is not None and selected_model_id is not None:
                    row = dst.execute(
                        "select models from model_cache where provider_id = ?",
                        (selected_provider,),
                    ).fetchone()
                    if row is not None:
                        try:
                            models = json.loads(row[0])
                        except (TypeError, json.JSONDecodeError):
                            models = []
                        if not isinstance(models, list):
                            models = []
                        models = [
                            model
                            for model in models
                            if isinstance(model, dict) and model.get("id") == selected_model_id
                        ]
                        dst.execute(
                            "update model_cache set models = ? where provider_id = ?",
                            (json.dumps(models, separators=(",", ":")), selected_provider),
                        )
    except sqlite3.Error as exc:
        raise SystemExit(f"failed to copy OMP model cache: {exc}") from exc
    return True

def gateway_models_yml(
    gateway_url: str,
    providers: list[str],
    model_ref: str = SANDBOX_MODEL_REF,
) -> str:
    selected_provider, selected_model_id = model_ref_parts(model_ref)
    if selected_provider not in providers:
        raise ValueError(
            f"gateway provider scope does not include selected model provider {selected_provider!r}"
        )
    lines = [
        "# Generated by Quant Bench sandbox_bwrap.py.",
        "# Routes the exact evaluated selector to host-side omp auth-gateway.",
        "providers:",
    ]
    metadata = host_provider_gateway_metadata(selected_provider)
    provider_base_url = (
        gateway_url.rstrip("/") + "/v1"
        if metadata.get("api") == "openai-completions"
        else gateway_url
    )
    lines.extend(
        [
            f"  {selected_provider}:",
            f"    baseUrl: {provider_base_url}",
            "    transport: pi-native",
            "    auth: none",
        ]
    )
    if isinstance(metadata.get("api"), str):
        lines.append(f"    api: {json.dumps(metadata['api'])}")
    if isinstance(metadata.get("compat"), dict) and metadata["compat"]:
        lines.append(f"    compat: {json.dumps(metadata['compat'], sort_keys=True)}")
    models = host_provider_models(selected_provider, selected_model_id)
    if not models:
        raise ValueError(
            f"host model configuration does not contain exact selector {model_ref!r}"
        )
    lines.append("    models:")
    for model in models:
        lines.append(f"      - {json.dumps(model, sort_keys=True)}")
    return "\n".join(lines) + "\n"

def safe_model_metadata(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: safe_model_metadata(item)
            for key, item in value.items()
            if key in SAFE_MODEL_KEYS or key in {"mode", "minLevel", "maxLevel"}
        }
    if isinstance(value, list):
        return [safe_model_metadata(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None

def gateway_safe_model_metadata(_provider: str, value: object) -> object:
    return safe_model_metadata(value)


def host_provider_config(provider: str) -> dict[str, object]:
    source_models = HOST_AGENT_DIR / "models.yml"
    if not source_models.exists():
        return {}
    try:
        import yaml  # type: ignore[import-not-found]

        parsed = yaml.safe_load(source_models.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    providers = parsed.get("providers")
    if not isinstance(providers, dict):
        return {}
    provider_config = providers.get(provider)
    if not isinstance(provider_config, dict):
        return {}
    return provider_config


def host_provider_gateway_metadata(provider: str) -> dict[str, object]:
    provider_config = host_provider_config(provider)
    metadata: dict[str, object] = {}
    api = provider_config.get("api")
    if isinstance(api, str):
        metadata["api"] = api
    compat = provider_config.get("compat")
    if isinstance(compat, dict):
        safe_compat = {
            key: value
            for key, value in compat.items()
            if key in SAFE_COMPAT_KEYS and isinstance(value, (str, int, float, bool, dict))
        }
        if safe_compat:
            metadata["compat"] = safe_compat
    return metadata


def host_provider_models(provider: str, selected_model_id: str | None = None) -> list[object]:
    provider_config = host_provider_config(provider)
    if not provider_config:
        return []
    models = provider_config.get("models")
    if not isinstance(models, list):
        return []
    sanitized = [gateway_safe_model_metadata(provider, model) for model in models]
    return [
        model
        for model in sanitized
        if isinstance(model, dict)
        and isinstance(model.get("id"), str)
        and (selected_model_id is None or model["id"] == selected_model_id)
    ]


def gateway_provider_scope(gateway_providers: list[str]) -> list[str]:
    return list(dict.fromkeys(provider for provider in gateway_providers if provider))


def sandbox_config_yml(model_ref: str = SANDBOX_MODEL_REF) -> str:
    model_ref_parts(model_ref)
    return f"""# Generated by Quant Bench sandbox_bwrap.py.
# Keep this credential-free; candidate runs must not receive host auth config.
defaultThinkingLevel: xhigh
modelRoles:
  default: {model_ref}
  task: {model_ref}
  plan: {model_ref}
  designer: {model_ref}
  reviewer: {model_ref}
  smol: {model_ref}
  vision: {model_ref}
"""


def sandbox_models_yml(model_ref: str = SANDBOX_MODEL_REF) -> str:
    provider, model_id = model_ref_parts(model_ref)
    placeholder_name = json.dumps(f"{model_id} sandbox placeholder")
    return f"""# Generated by Quant Bench sandbox_bwrap.py.
# Credential-free placeholder for no-gateway sandbox commands.
providers:
  {provider}:
    auth: none
    models:
      - id: {json.dumps(model_id)}
        name: {placeholder_name}
        contextWindow: 1
        maxTokens: 1
        reasoning:
          minLevel: minimal
          maxLevel: xhigh
"""

def require_loopback_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("--auth-gateway-url must be an http://127.0.0.1 or http://localhost URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SystemExit("--auth-gateway-url must include a numeric port") from exc
    if port is None:
        raise SystemExit("--auth-gateway-url must include a numeric port")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise SystemExit("--auth-gateway-url must be a bare loopback origin, not a path/query/fragment URL")
    if parsed.username or parsed.password:
        raise SystemExit("--auth-gateway-url must not contain credentials")
    return f"{parsed.scheme}://{parsed.hostname}:{port}"


def prepare_fake_home(
    fake_home: Path,
    *,
    auth_gateway_url: str | None,
    gateway_providers: list[str],
    model_ref: str = SANDBOX_MODEL_REF,
) -> None:
    selected_provider, _selected_model_id = model_ref_parts(model_ref)
    agent_dir = fake_home / ".omp" / "agent"
    agents_dir = agent_dir / "agents"
    for subdir in (
        fake_home / ".cache",
        fake_home / ".local" / "share",
        fake_home / ".local" / "state",
        agents_dir,
    ):
        subdir.mkdir(parents=True, exist_ok=True)

    source_agents = HOST_AGENT_DIR / "agents"
    if source_agents.exists():
        for agent_file in sorted(source_agents.glob("*.md")):
            shutil.copy2(agent_file, agents_dir / agent_file.name)

    if auth_gateway_url:
        requested_scope = gateway_provider_scope(gateway_providers) or [selected_provider]
        if selected_provider not in requested_scope:
            raise ValueError(
                f"gateway provider scope does not include selected model provider {selected_provider!r}"
            )
        gateway_providers_scope = [selected_provider]
    else:
        gateway_providers_scope = []
    copy_model_cache(
        HOST_AGENT_DIR,
        agent_dir,
        allowed_providers={selected_provider},
        allowed_model_ref=model_ref,
    )

    (agent_dir / "config.yml").write_text(sandbox_config_yml(model_ref), encoding="utf-8")

    if auth_gateway_url:
        (agent_dir / "models.yml").write_text(
            gateway_models_yml(auth_gateway_url, gateway_providers_scope, model_ref),
            encoding="utf-8",
        )
    else:
        (agent_dir / "models.yml").write_text(sandbox_models_yml(model_ref), encoding="utf-8")

    # Never copy live credential/session state into the candidate sandbox.
    forbidden = [
        ".env",
        "agent.db",
        "agent.db-shm",
        "agent.db-wal",
        "history.db",
        "history.db-shm",
        "history.db-wal",
        "autoqa.db",
        "sessions",
        "blobs",
        "terminal-sessions",
    ]
    for name in forbidden:
        target = agent_dir / name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()


def bwrap_args(
    *,
    workspace: Path,
    fake_home: Path,
    command: list[str],
    share_net: bool,
    allowed_env: list[str],
) -> list[str]:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise SystemExit("bwrap is not installed")
    require_path(HOST_BUN_DIR, "Bun/OMP runtime")

    args = [
        bwrap,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/run",
        "--dir",
        "/opt",
        "--dir",
        "/home",
        "--dir",
        str(SANDBOX_HOME),
        "--bind",
        str(workspace),
        str(SANDBOX_WORKSPACE),
        "--bind",
        str(fake_home),
        str(SANDBOX_HOME),
        "--dir",
        str(SANDBOX_RUNTIME_DIR),
        "--ro-bind",
        str(HOST_BUN_DIR),
        str(SANDBOX_RUNTIME_DIR),
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind-try",
        "/lib64",
        "/lib64",
        "--ro-bind-try",
        "/etc/ssl",
        "/etc/ssl",
        "--ro-bind-try",
        "/etc/ca-certificates",
        "/etc/ca-certificates",
        "--ro-bind-try",
        "/etc/resolv.conf",
        "/etc/resolv.conf",
        "--ro-bind-try",
        "/etc/hosts",
        "/etc/hosts",
        "--ro-bind-try",
        "/etc/nsswitch.conf",
        "/etc/nsswitch.conf",
        "--clearenv",
        "--setenv",
        "HOME",
        str(SANDBOX_HOME),
        "--setenv",
        "USER",
        "agent",
        "--setenv",
        "LOGNAME",
        "agent",
        "--setenv",
        "PATH",
        f"{SANDBOX_RUNTIME_DIR}/bin:/usr/local/bin:/usr/bin:/bin",
        "--setenv",
        "BUN_INSTALL",
        str(SANDBOX_RUNTIME_DIR),
        "--setenv",
        "PI_CODING_AGENT_DIR",
        str(SANDBOX_AGENT_DIR),
        "--setenv",
        "XDG_CACHE_HOME",
        "/home/agent/.cache",
        "--setenv",
        "XDG_DATA_HOME",
        "/home/agent/.local/share",
        "--setenv",
        "XDG_STATE_HOME",
        "/home/agent/.local/state",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "TERM",
        "dumb",
        "--chdir",
        str(SANDBOX_WORKSPACE),
    ]
    if share_net:
        args.insert(2, "--share-net")
    for name in allowed_env:
        if name in os.environ:
            args.extend(["--setenv", name, os.environ[name]])
    args.extend(command)
    return args


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a command in the Quant Bench bwrap sandbox.")
    parser.add_argument("--workspace", required=True, help="Host workspace path to mount as /workspace.")
    parser.add_argument("--sandbox-root", required=True, help="Host directory for generated fake home/config.")
    parser.add_argument("--share-net", action="store_true", help="Share host network namespace for live model calls.")
    parser.add_argument(
        "--auth-gateway-url",
        help="Generate sandbox models.yml provider overrides that route through this auth-gateway URL.",
    )
    parser.add_argument(
        "--gateway-provider",
        action="append",
        default=[],
        help="Provider to route through auth-gateway. Defaults to the selected model provider.",
    )
    parser.add_argument(
        "--allow-env",
        action="append",
        default=[],
        help="Explicit environment variable to pass through. Repeatable.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("missing command after --", file=sys.stderr)
        return 2
    try:
        model_ref = model_selector_from_command(command, required=bool(args.auth_gateway_url))
        auth_gateway_url = (
            require_loopback_http_url(args.auth_gateway_url) if args.auth_gateway_url else None
        )
        workspace = require_path(Path(args.workspace), "workspace")
    except (ValueError, SystemExit) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    sandbox_root = Path(args.sandbox_root).resolve()
    fake_home = sandbox_root / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    try:
        prepare_fake_home(
            fake_home,
            auth_gateway_url=auth_gateway_url,
            gateway_providers=args.gateway_provider,
            model_ref=model_ref,
        )
    except (ValueError, SystemExit) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    proc = subprocess.run(
        bwrap_args(
            workspace=workspace,
            fake_home=fake_home,
            command=command,
            share_net=args.share_net,
            allowed_env=args.allow_env,
        ),
        text=True,
    )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
