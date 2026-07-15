from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTH_MODULE_PATH = PROJECT_ROOT / "scripts" / "auth_gateway.py"
GATEWAY_SOCKET_MODULE_PATH = PROJECT_ROOT / "scripts" / "gateway_socket_proxy.py"

def _load_module(name: str, relative_path: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


metrics_capture = _load_module("omp_metrics_capture", "scripts/omp_metrics_capture.py")
sandbox_bwrap = _load_module("sandbox_bwrap", "scripts/sandbox_bwrap.py")
auth_gateway = _load_module("auth_gateway", "scripts/auth_gateway.py")
gateway_socket_proxy = _load_module("gateway_socket_proxy", "scripts/gateway_socket_proxy.py")


class SandboxGatewayTests(unittest.TestCase):
    def test_auth_gateway_child_env_is_minimal(self) -> None:
        previous = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "must-not-leak"
        try:
            env = auth_gateway.minimal_child_env({"OMP_AUTH_BROKER_TOKEN": "token"})
        finally:
            if previous is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous
        self.assertIn("OMP_AUTH_BROKER_TOKEN", env)
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_auth_gateway_provider_env_allows_selected_provider_keys(self) -> None:
        provider_keys = ("ALIBABA_TOKEN_PLAN_API_KEY", "GMI_API_KEY", "NVIDIA_API_KEY", "OPENAI_API_KEY", "WAFER_PASS_API_KEY", "WAFER_SERVERLESS_API_KEY", "ZAI_API_KEY")
        previous = {key: os.environ.get(key) for key in provider_keys}
        os.environ["ALIBABA_TOKEN_PLAN_API_KEY"] = "alibaba-token"
        os.environ["GMI_API_KEY"] = "gmi-token"
        os.environ["NVIDIA_API_KEY"] = "nvidia-token"
        os.environ["OPENAI_API_KEY"] = "openai-token"
        os.environ["WAFER_PASS_API_KEY"] = "wafer-pass-token"
        os.environ["WAFER_SERVERLESS_API_KEY"] = "wafer-serverless-token"
        os.environ["ZAI_API_KEY"] = "zai-token"
        try:
            broker_env = auth_gateway.auth_broker_child_env()
            gateway_env = auth_gateway.auth_gateway_child_env({"OMP_AUTH_BROKER_TOKEN": "token"})
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        for env in (broker_env, gateway_env):
            self.assertEqual(env["ALIBABA_TOKEN_PLAN_API_KEY"], "alibaba-token")
            self.assertEqual(env["NVIDIA_API_KEY"], "nvidia-token")
            self.assertEqual(env["GMI_API_KEY"], "gmi-token")
            self.assertEqual(env["OPENAI_API_KEY"], "openai-token")
            self.assertEqual(env["WAFER_PASS_API_KEY"], "wafer-pass-token")
            self.assertEqual(env["WAFER_SERVERLESS_API_KEY"], "wafer-serverless-token")
            self.assertEqual(env["ZAI_API_KEY"], "zai-token")

    def test_auth_gateway_temp_agent_config_contains_route_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_agent = Path(tmp) / "source"
            source_agent.mkdir()
            (source_agent / "models.yml").write_text(
                "providers:\n"
                "  alibaba-token-plan:\n"
                "    apiKey: \"ALIBABA_TOKEN_PLAN_API_KEY\"\n"
                "  gmi:\n"
                "    apiKey: GMI_API_KEY\n"
                "  wafer-pass:\n"
                "    apiKey: WAFER_PASS_API_KEY\n"
                "  wafer-serverless:\n"
                "    apiKey: \"WAFER_SERVERLESS_API_KEY\"\n"
                "  wafer-cmd-provider:\n"
                "    apiKey: \"!python3 /home/example/.omp/agent/bin/omp-api-key.py wafer\"\n"
                "  arbitrary-cmd-provider:\n"
                "    apiKey: \"!python3 /home/example/.omp/agent/bin/other-key.py wafer\"\n"
                "  inline-secret-provider: {apiKey: inline-secret, baseUrl: https://example.invalid/v1}\n"
                "  inline-quoted-secret-provider: {\"clientSecret\": \"quoted-inline-secret\", baseUrl: https://example.invalid/v1}\n"
                "  inline-auth-secret-provider: {auth: \"Bearer inline-auth-secret\", baseUrl: https://example.invalid/v1}\n"
                "  literal-secret-provider:\n"
                "    apiKey: live-secret\n"
                "    secondaryApiKey: \"$OPENAI_API_KEY:fallback-secret\"\n"
                "    baseUrl: https://user:url-secret@example.invalid/v1?api_key=query-secret\n"
                "    secretKey: secret-key-value\n"
                "    apiSecret: api-secret-value\n"
                "    accessKeyId: access-key-value\n"
                "    privateKey: |\n"
                "      PRIVATEKEYVALUE\n"
                "    accessToken: live-access-token\n"
                "    clientSecret: live-client-secret\n"
                "    refreshToken: |\n"
                "\n"
                "      PRODREFRESH456\n"
                "      PRODREFRESH123\n"
                "    headers:\n"
                "      Authorization: Bearer literal-header-secret\n"
                "  env-header-provider:\n"
                "    headers:\n"
                "      Authorization: Bearer $XAI_OAUTH_TOKEN\n"
                "      X-Api-Key: $XAI_OAUTH_TOKEN header-fallback-secret\n"
                "  safe-auth-provider:\n"
                "    auth: none\n"
                "  literal-auth-provider:\n"
                "    auth: Bearer auth-secret\n",
                encoding="utf-8",
            )
            agent_dir = Path(tmp) / "agent"
            auth_gateway.prepare_gateway_agent_dir(agent_dir, source_agent_dir=source_agent)
            models_yml = (agent_dir / "models.yml").read_text(encoding="utf-8")

        self.assertIn("alibaba-token-plan:", models_yml)
        self.assertIn("apiKey: \"ALIBABA_TOKEN_PLAN_API_KEY\"", models_yml)
        self.assertIn("gmi:", models_yml)
        self.assertIn("apiKey: GMI_API_KEY", models_yml)
        self.assertIn("wafer-pass:", models_yml)
        self.assertIn("apiKey: WAFER_PASS_API_KEY", models_yml)
        self.assertIn("wafer-serverless:", models_yml)
        self.assertIn("apiKey: \"WAFER_SERVERLESS_API_KEY\"", models_yml)
        self.assertIn("Authorization: Bearer $XAI_OAUTH_TOKEN", models_yml)
        self.assertIn("auth: none", models_yml)
        self.assertIn("wafer-cmd-provider:", models_yml)
        self.assertIn('apiKey: "!python3 /home/example/.omp/agent/bin/omp-api-key.py wafer"', models_yml)
        self.assertNotIn("other-key.py wafer", models_yml)
        self.assertNotIn("live-secret", models_yml)
        self.assertNotIn("live-access-token", models_yml)
        self.assertNotIn("live-client-secret", models_yml)
        self.assertNotIn("PRODREFRESH123", models_yml)
        self.assertNotIn("PRODREFRESH456", models_yml)
        self.assertNotIn("fallback-secret", models_yml)
        self.assertNotIn("header-fallback-secret", models_yml)
        self.assertNotIn("url-secret", models_yml)
        self.assertNotIn("query-secret", models_yml)
        self.assertNotIn("secret-key-value", models_yml)
        self.assertNotIn("api-secret-value", models_yml)
        self.assertNotIn("access-key-value", models_yml)
        self.assertNotIn("PRIVATEKEYVALUE", models_yml)
        self.assertNotIn("inline-secret", models_yml)
        self.assertNotIn("quoted-inline-secret", models_yml)
        self.assertNotIn("inline-auth-secret", models_yml)
        self.assertNotIn("auth-secret", models_yml)
        self.assertNotIn("OMITTED_LITERAL_API_KEY", models_yml)
        self.assertNotIn("literal-header-secret", models_yml)


    def test_auth_gateway_uses_configured_agent_dir_for_env_and_models(self) -> None:
        previous_dir = os.environ.get("PI_CODING_AGENT_DIR")
        previous_openai = os.environ.get("OPENAI_API_KEY")
        with tempfile.TemporaryDirectory() as tmp:
            source_agent = Path(tmp) / "source"
            source_agent.mkdir()
            (source_agent / ".env").write_text("OPENAI_API_KEY=file-token\n", encoding="utf-8")
            (source_agent / "models.yml").write_text(
                "providers:\n  openai-codex:\n    apiKey: OPENAI_API_KEY\n",
                encoding="utf-8",
            )
            os.environ["PI_CODING_AGENT_DIR"] = str(source_agent)
            os.environ.pop("OPENAI_API_KEY", None)
            try:
                selected_env = auth_gateway.selected_provider_env()
                agent_dir = Path(tmp) / "agent"
                auth_gateway.prepare_gateway_agent_dir(agent_dir)
                models_yml = (agent_dir / "models.yml").read_text(encoding="utf-8")
            finally:
                if previous_dir is None:
                    os.environ.pop("PI_CODING_AGENT_DIR", None)
                else:
                    os.environ["PI_CODING_AGENT_DIR"] = previous_dir
                if previous_openai is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = previous_openai

        self.assertEqual(selected_env["OPENAI_API_KEY"], "file-token")
        self.assertIn("openai-codex:", models_yml)

    def test_omp_json_capture_aggregates_multi_turn_usage(self) -> None:
        first_turn = {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "toolCall", "name": "read", "args": {}}],
                "provider": "openai-codex",
                "api": "openai-codex-responses",
                "model": "gpt-5.6-sol",
                "usage": {
                    "input": 10,
                    "output": 5,
                    "cacheRead": 20,
                    "cacheWrite": 0,
                    "totalTokens": 35,
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
                },
                "duration": 300,
                "ttft": 100,
                "stopReason": "toolUse",
            },
        }
        final_turn = {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": '{"bucket":"scout"}'}],
                "provider": "openai-codex",
                "api": "openai-codex-responses",
                "model": "gpt-5.6-sol",
                "usage": {
                    "input": 30,
                    "output": 15,
                    "cacheRead": 10,
                    "cacheWrite": 5,
                    "totalTokens": 60,
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
                },
                "duration": 700,
                "ttft": 200,
                "stopReason": "stop",
            },
        }
        run = {
            "returncode": 0,
            "elapsed_sec": 1.1,
            "stdout": json.dumps(first_turn) + "\n" + json.dumps(final_turn) + "\n",
            "stderr": "",
        }

        metrics_capture.capture_omp_json_stdout(run)

        self.assertEqual(run["stdout"], '{"bucket":"scout"}')
        self.assertEqual(run["usage"]["omp_assistant_turns"], 2)
        self.assertEqual(run["usage"]["input_tokens"], 75)
        self.assertEqual(run["usage"]["output_tokens"], 20)
        self.assertEqual(run["usage"]["total_tokens"], 95)
        self.assertEqual(run["usage"]["cached_input_tokens"], 30)
        self.assertEqual(run["usage"]["cache_write_input_tokens"], 5)
        self.assertEqual(run["usage"]["ttft_ms"], 150)
        self.assertEqual(run["usage"]["generation_ms"], 700)

    def test_omp_json_capture_preserves_provider_error_status(self) -> None:
        error_turn = {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [],
                "provider": "openai-codex",
                "api": "openai-codex-responses",
                "model": "gpt-5.6-sol",
                "usage": {
                    "input": 1,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "totalTokens": 1,
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
                },
                "duration": 50,
                "ttft": 0,
                "stopReason": "error",
                "errorMessage": "provider 429 rate_limit_exceeded",
            },
        }
        run = {
            "returncode": 0,
            "elapsed_sec": 0.05,
            "stdout": json.dumps(error_turn) + "\n",
            "stderr": "extension warning",
        }

        metrics_capture.capture_omp_json_stdout(run)

        self.assertEqual(run["returncode"], 1)
        self.assertEqual(run["stderr"], "extension warning\nprovider 429 rate_limit_exceeded")
        self.assertEqual(run["omp_error_message"], "provider 429 rate_limit_exceeded")

    def test_omp_json_capture_preserves_nonterminal_error_message(self) -> None:
        assistant = {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": '{"ok": true}'}],
                "usage": {
                    "input": 1,
                    "output": 1,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "totalTokens": 2,
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
                },
                "duration": 40,
                "ttft": 10,
                "stopReason": "stop",
                "errorMessage": "provider fallback warning",
            },
        }
        run = {
            "returncode": 0,
            "elapsed_sec": 0.04,
            "stdout": json.dumps(assistant) + "\n",
            "stderr": "extension warning",
        }

        metrics_capture.capture_omp_json_stdout(run)

        self.assertEqual(run["returncode"], 0)
        self.assertEqual(run["stdout"], '{"ok": true}')
        self.assertEqual(run["stderr"], "extension warning\nprovider fallback warning")
        self.assertEqual(run["omp_error_message"], "provider fallback warning")

    def test_omp_json_capture_uses_agent_end_fallback(self) -> None:
        assistant = {
            "role": "assistant",
            "content": [{"type": "text", "text": ""}],
            "provider": "openai-codex",
            "api": "openai-codex-responses",
            "model": "gpt-5.6-sol",
            "usage": {
                "input": 2,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 2,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
            },
            "duration": 80,
            "ttft": 0,
            "stopReason": "error",
            "errorMessage": "auth failed for provider",
        }
        run = {
            "returncode": 0,
            "elapsed_sec": 0.08,
            "stdout": json.dumps({"type": "agent_end", "messages": [assistant]}) + "\n",
            "stderr": "",
        }

        metrics_capture.capture_omp_json_stdout(run)

        self.assertEqual(run["returncode"], 1)
        self.assertEqual(run["stderr"], "auth failed for provider")
        self.assertEqual(run["usage"]["input_tokens"], 2)
        self.assertEqual(run["usage"]["generation_ms"], 80)

    def test_omp_json_capture_prefers_terminal_agent_end_error(self) -> None:
        tool_turn = {
            "role": "assistant",
            "content": [{"type": "toolUse", "name": "read", "args": {}}],
            "usage": {
                "input": 3,
                "output": 2,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 5,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
            },
            "duration": 50,
            "ttft": 10,
            "stopReason": "tool_use",
        }
        terminal_error = {
            "role": "assistant",
            "content": [],
            "usage": {
                "input": 1,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 1,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
            },
            "duration": 20,
            "ttft": 0,
            "stopReason": "error",
            "errorMessage": "tool follow-up provider 429",
        }
        run = {
            "returncode": 0,
            "elapsed_sec": 0.07,
            "stdout": (
                json.dumps({"type": "message_end", "message": tool_turn})
                + "\n"
                + json.dumps({"type": "agent_end", "messages": [tool_turn, terminal_error]})
                + "\n"
            ),
            "stderr": "",
        }

        metrics_capture.capture_omp_json_stdout(run)

        self.assertEqual(run["returncode"], 1)
        self.assertEqual(run["stdout"], "")
        self.assertEqual(run["stderr"], "tool follow-up provider 429")
        self.assertEqual(run["usage"]["input_tokens"], 4)
        self.assertEqual(run["usage"]["output_tokens"], 2)

    def test_omp_json_capture_synthesizes_empty_error_message(self) -> None:
        assistant = {
            "role": "assistant",
            "content": [{"type": "text", "text": '{"ok":true}'}],
            "usage": {
                "input": 1,
                "output": 1,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 2,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
            },
            "duration": 10,
            "stopReason": "error",
        }
        run = {
            "returncode": 0,
            "elapsed_sec": 0.01,
            "stdout": json.dumps({"type": "agent_end", "messages": [assistant]}) + "\n",
            "stderr": "",
        }

        metrics_capture.capture_omp_json_stdout(run)

        self.assertEqual(run["returncode"], 1)
        self.assertEqual(run["stderr"], "Request error")
        self.assertEqual(run["omp_error_message"], "Request error")

    def test_omp_json_file_capture_aggregates_many_turns_incrementally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agent.jsonl"
            with path.open("w", encoding="utf-8") as handle:
                for index in range(200):
                    handle.write(json.dumps({
                        "type": "message_end",
                        "message": {
                            "role": "assistant",
                            "content": "x" * 10_000 if index < 199 else "final",
                            "usage": {
                                "input": 1,
                                "output": 2,
                                "totalTokens": 3,
                            },
                            "stopReason": "stop",
                        },
                    }) + "\n")
            run = {"returncode": 0, "stdout": "", "stderr": ""}
            metrics_capture.capture_omp_json_file(run, path)

        self.assertEqual(run["stdout"], "final")
        self.assertEqual(run["usage"]["omp_assistant_turns"], 200)
        self.assertEqual(run["usage"]["input_tokens"], 200)
        self.assertEqual(run["usage"]["output_tokens"], 400)
        self.assertEqual(run["usage"]["total_tokens"], 600)

    def test_oversized_agent_end_error_retains_prior_incremental_usage(self) -> None:
        message_end = {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": "tool result",
                "usage": {"input": 7, "output": 3, "totalTokens": 10},
                "stopReason": "tool_use",
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agent.jsonl"
            with path.open("wb") as handle:
                handle.write((json.dumps(message_end) + "\n").encode())
                handle.write(
                    b'{"type":"agent_end","messages":["'
                    + b"x" * 1_100_000
                    + b'"],"stopReason":"aborted"}\n'
                )
            run = {"returncode": 0, "stdout": "", "stderr": ""}
            metrics_capture.capture_omp_json_file(run, path)

        self.assertEqual(run["returncode"], 1)
        self.assertEqual(run["omp_stop_reason"], "aborted")
        self.assertEqual(run["usage"]["input_tokens"], 7)
        self.assertEqual(run["usage"]["output_tokens"], 3)
        self.assertEqual(run["usage"]["total_tokens"], 10)

    def test_runtime_metrics_normalize_provider_usage_and_cache_reads(self) -> None:
        metrics = metrics_capture.runtime_metrics_for_run(
            {
                "elapsed_sec": 2,
                "stdout": '{"ok": true}',
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "total_tokens": 1200,
                    "input_tokens_details": {"cached_tokens": 800},
                    "output_tokens_details": {"reasoning_tokens": 25},
                    "ttft_ms": 150,
                    "generation_ms": 1800,
                    "service_tier": "priority",
                    "region": "us-east",
                },
            },
            model="openai-codex/gpt-5.6-sol:xhigh",
            auth_gateway_url="http://127.0.0.1:8000",
        )

        self.assertEqual(list(metrics), list(metrics_capture.RUNTIME_METRIC_KEYS))
        self.assertEqual(metrics["source"], "provider_usage")
        self.assertEqual(metrics["latency"]["wall_ms"], 2000)
        self.assertEqual(metrics["latency"]["ttft_ms"], 150)
        self.assertEqual(metrics["tokens"]["input"], 1000)
        self.assertEqual(metrics["tokens"]["output"], 200)
        self.assertEqual(metrics["tokens"]["reasoning_output"], 25)
        self.assertEqual(metrics["cache"]["input_cached"], 800)
        self.assertEqual(metrics["cache"]["input_uncached"], 200)
        self.assertEqual(metrics["cache"]["cache_read_ratio"], 0.8)
        self.assertTrue(metrics["cache"]["prompt_cache_hit"])
        self.assertEqual(metrics["throughput"]["output_tok_s"], 111.111)
        self.assertEqual(metrics["throughput"]["wall_output_tok_s"], 100.0)
        self.assertEqual(metrics["provider_route"]["provider"], "openai-codex")
        self.assertEqual(metrics["provider_route"]["model_id"], "gpt-5.6-sol")
        self.assertTrue(metrics["provider_route"]["auth_gateway"])
        self.assertEqual(metrics["provider_route"]["service_tier"], "priority")
        self.assertEqual(metrics["provider_route"]["region"], "us-east")

        luna_metrics = metrics_capture.runtime_metrics_for_run(
            {
                "elapsed_sec": 2,
                "stdout": "",
                "usage": {
                    "input_tokens": 150,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 1472,
                    "cache_creation_input_tokens": 128,
                },
            },
            model="openai-codex/gpt-5.6-luna",
        )

        self.assertEqual(luna_metrics["tokens"]["input"], 1750)
        self.assertEqual(luna_metrics["tokens"]["total"], 1800)
        self.assertEqual(luna_metrics["cache"]["input_cached"], 1472)
        self.assertEqual(luna_metrics["cache"]["input_cache_write"], 128)
        self.assertEqual(luna_metrics["cache"]["input_uncached"], 278)
        self.assertEqual(luna_metrics["cache"]["cache_read_ratio"], 0.8411)

    def test_runtime_metrics_keep_response_cache_separate_from_prompt_cache(self) -> None:
        metrics = metrics_capture.runtime_metrics_for_run(
            {
                "elapsed_sec": 1,
                "stdout": "",
                "proxy_usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "response_cache_hit": True,
                },
            },
            model="devin/swe-1-7",
        )

        self.assertEqual(metrics["source"], "proxy_usage")
        self.assertTrue(metrics["cache"]["response_cache_hit"])
        self.assertIsNone(metrics["cache"]["prompt_cache_hit"])
        self.assertIsNone(metrics["cache"]["cache_read_ratio"])
        self.assertIsNone(metrics["throughput"]["output_tok_s"])
        self.assertEqual(metrics["throughput"]["wall_output_tok_s"], 5.0)
        self.assertEqual(metrics["throughput"]["visible_output_tok_s_est"], 0.0)

    def test_runtime_metrics_prefers_gateway_metric_line_over_omp_usage(self) -> None:
        metrics = metrics_capture.runtime_metrics_for_run(
            {
                "elapsed_sec": 2,
                "stdout": "",
                "usage": {"input_tokens": 10, "output_tokens": 1, "generation_ms": 1000},
                "stderr": "OMP_USAGE_JSON="
                + json.dumps(
                    {
                        "source": "proxy_gateway",
                        "input_tokens": 10,
                        "output_tokens": 7,
                        "generation_ms": 1000,
                        "input_tokens_details": {"cached_tokens": 5},
                    }
                ),
            },
            model="openai-codex/gpt-5.6-sol:xhigh",
        )

        self.assertEqual(metrics["source"], "proxy_usage")
        self.assertEqual(metrics["tokens"]["output"], 7)
        self.assertEqual(metrics["cache"]["input_cached"], 5)
        self.assertEqual(metrics["throughput"]["output_tok_s"], 7.0)

    def test_runtime_metrics_summary_aggregates_without_changing_scores(self) -> None:
        rows = [
            {
                "gate": "base_format",
                "passed": True,
                "runtime_metrics": metrics_capture.runtime_metrics_for_run(
                    {
                        "elapsed_sec": 2,
                        "stdout": '{"ok": true}',
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 20,
                            "input_tokens_details": {"cached_tokens": 50},
                            "ttft_ms": 100,
                            "generation_ms": 1000,
                        },
                    },
                    model="openai-codex/gpt-5.6-sol:xhigh",
                ),
            },
            {
                "gate": "tool_loop",
                "passed": False,
                "runtime_metrics": metrics_capture.runtime_metrics_for_run(
                    {
                        "elapsed_sec": 3,
                        "stdout": '{"ok": false}',
                        "usage": {
                            "input_tokens": 200,
                            "output_tokens": 30,
                            "input_tokens_details": {"cached_tokens": 150},
                            "ttft_ms": 200,
                            "generation_ms": 1000,
                        },
                    },
                    model="openai-codex/gpt-5.6-sol:xhigh",
                ),
            },
        ]

        summary = metrics_capture.runtime_metrics_summary(rows)

        self.assertTrue(rows[0]["passed"])
        self.assertFalse(rows[1]["passed"])
        self.assertEqual(summary["source"], "provider_usage")
        self.assertEqual(summary["latency"]["wall_ms"], 5000)
        self.assertEqual(summary["tokens"]["input"], 300)
        self.assertEqual(summary["tokens"]["output"], 50)
        self.assertEqual(summary["cache"]["input_cached"], 200)
        self.assertEqual(summary["cache"]["cache_read_ratio"], 0.6667)
        self.assertEqual(summary["latency"]["ttft_ms"], 150)
        self.assertEqual(summary["latency"]["generation_ms"], 2000)
        self.assertEqual(summary["throughput"]["output_tok_s"], 25.0)
        self.assertEqual(summary["throughput"]["wall_output_tok_s"], 10.0)

    def test_runtime_metrics_summary_nulls_partial_provider_token_totals(self) -> None:
        rows = [
            {
                "gate": "base_format",
                "passed": True,
                "runtime_metrics": metrics_capture.runtime_metrics_for_run(
                    {
                        "elapsed_sec": 2,
                        "stdout": '{"ok": true}',
                        "usage": {"input_tokens": 100, "output_tokens": 20},
                    },
                    model="openai-codex/gpt-5.6-sol:xhigh",
                ),
            },
            {
                "gate": "tool_loop",
                "passed": True,
                "runtime_metrics": metrics_capture.runtime_metrics_for_run(
                    {"elapsed_sec": 1, "stdout": ""},
                    model="openai-codex/gpt-5.6-sol:xhigh",
                ),
            },
        ]

        summary = metrics_capture.runtime_metrics_summary(rows)
        metrics = summary

        self.assertIsNone(metrics["tokens"]["input"])
        self.assertIsNone(metrics["tokens"]["output"])
        self.assertIsNone(metrics["tokens"]["total"])
        self.assertEqual(metrics["tokens"]["visible_output_est"], 3)
        self.assertIsNone(metrics["throughput"]["wall_output_tok_s"])
        self.assertEqual(metrics["throughput"]["visible_output_tok_s_est"], 1.0)
        self.assertEqual(metrics["notes"]["coverage"]["input_tokens"], {"known": 1, "total": 2})
        self.assertEqual(metrics["notes"]["coverage"]["output_tokens"], {"known": 1, "total": 2})


    def test_sandbox_copies_model_cache_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_agent = root / "src"
            dst_agent = root / "dst"
            src_agent.mkdir()
            dst_agent.mkdir()
            with sqlite3.connect(src_agent / "models.db") as db:
                db.execute(
                    """
                    create table model_cache (
                        provider_id text primary key,
                        version integer not null,
                        updated_at integer not null,
                        authoritative integer not null default 0,
                        static_fingerprint text not null default '',
                        models text not null
                    )
                    """
                )
                db.execute(
                    "insert into model_cache values (?, ?, ?, ?, ?, ?)",
                    (
                        "openai-codex",
                        3,
                        1780671290688,
                        1,
                        "fixture",
                        '[{"provider":"openai-codex","id":"gpt-5.6-sol","maxTokens":65536}]',
                    ),
                )

            self.assertTrue(sandbox_bwrap.copy_model_cache(src_agent, dst_agent))
            with sqlite3.connect(dst_agent / "models.db") as db:
                row = db.execute(
                    "select provider_id, models from model_cache where provider_id = ?",
                    ("openai-codex",),
                ).fetchone()

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row[0], "openai-codex")
        self.assertIn('"id":"gpt-5.6-sol"', row[1])
        self.assertIn('"maxTokens":65536', row[1])

    def test_sandbox_auth_gateway_filters_to_exact_requested_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_agent = root / "source"
            fake_home = root / "fake-home"
            source_agent.mkdir()
            (source_agent / "agents").mkdir()
            (source_agent / "models.yml").write_text(
                """
providers:
  openai-codex:
    baseUrl: https://openai.example/v1
    api: openai-responses
    models:
      - id: gpt-5.6-sol
        maxTokens: 65536
        reasoning: true
      - id: gpt-5.6-luna
        maxTokens: 65536
        reasoning: true
""",
                encoding="utf-8",
            )
            with sqlite3.connect(source_agent / "models.db") as db:
                db.execute(
                    """
                    create table model_cache (
                        provider_id text primary key,
                        version integer not null,
                        updated_at integer not null,
                        authoritative integer not null default 0,
                        static_fingerprint text not null default '',
                        models text not null
                    )
                    """
                )
                db.execute(
                    "insert into model_cache values (?, ?, ?, ?, ?, ?)",
                    (
                        "openai-codex",
                        3,
                        1780671290688,
                        1,
                        "fixture",
                        '[{"id":"gpt-5.6-sol"},{"id":"gpt-5.6-luna"}]',
                    ),
                )

            original_host_agent_dir = sandbox_bwrap.HOST_AGENT_DIR
            try:
                sandbox_bwrap.HOST_AGENT_DIR = source_agent
                sandbox_bwrap.prepare_fake_home(
                    fake_home,
                    auth_gateway_url="http://127.0.0.1:1234",
                    gateway_providers=["openai-codex"],
                    model_ref="openai-codex/gpt-5.6-sol:max",
                )
            finally:
                sandbox_bwrap.HOST_AGENT_DIR = original_host_agent_dir

            models_yml = (fake_home / ".omp" / "agent" / "models.yml").read_text(encoding="utf-8")
            with sqlite3.connect(fake_home / ".omp" / "agent" / "models.db") as db:
                provider_rows = [
                    row[0] for row in db.execute("select provider_id from model_cache order by provider_id")
                ]
                cached_models = json.loads(
                    db.execute(
                        "select models from model_cache where provider_id = ?", ("openai-codex",)
                    ).fetchone()[0]
                )

        self.assertIn("  openai-codex:", models_yml)
        self.assertIn('"id": "gpt-5.6-sol"', models_yml)
        self.assertNotIn("gpt-5.6-luna", models_yml)
        self.assertEqual(["openai-codex"], provider_rows)
        self.assertEqual(["gpt-5.6-sol"], [model["id"] for model in cached_models])

    def test_sandbox_gateway_provider_scope_deduplicates(self) -> None:
        self.assertEqual(
            ["openai-codex"],
            sandbox_bwrap.gateway_provider_scope(["openai-codex", "openai-codex"]),
        )


    def test_sandbox_gateway_config_contains_only_requested_model(self) -> None:
        original_host_config = sandbox_bwrap.host_provider_config
        sandbox_bwrap.host_provider_config = lambda _provider: {
            "api": "openai-responses",
            "models": [
                {"id": "gpt-5.6-sol", "maxTokens": 65536},
                {"id": "gpt-5.6-luna", "maxTokens": 65536},
            ],
        }
        try:
            models_yml = sandbox_bwrap.gateway_models_yml(
                "http://127.0.0.1:1234",
                ["openai-codex"],
                model_ref="openai-codex/gpt-5.6-sol:max",
            )
        finally:
            sandbox_bwrap.host_provider_config = original_host_config

        self.assertEqual(models_yml.count("baseUrl: http://127.0.0.1:1234\n"), 1)
        self.assertIn('"id": "gpt-5.6-sol"', models_yml)
        self.assertNotIn("gpt-5.6-luna", models_yml)

    def test_sandbox_no_gateway_models_yml_is_credential_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            host_agent = root / "host"
            fake_home = root / "fake-home"
            host_agent.mkdir()
            (host_agent / "models.yml").write_text(
                "providers:\n  openai-codex:\n    apiKey: live-secret\n    baseUrl: https://live.example\n",
                encoding="utf-8",
            )

            original_host_agent_dir = sandbox_bwrap.HOST_AGENT_DIR
            sandbox_bwrap.HOST_AGENT_DIR = host_agent
            try:
                sandbox_bwrap.prepare_fake_home(fake_home, auth_gateway_url=None, gateway_providers=[])
            finally:
                sandbox_bwrap.HOST_AGENT_DIR = original_host_agent_dir

            models_yml = (fake_home / ".omp" / "agent" / "models.yml").read_text(encoding="utf-8")

        self.assertIn("Credential-free placeholder", models_yml)
        self.assertNotIn("live-secret", models_yml)
        self.assertNotIn("live.example", models_yml)

    def test_gateway_socket_proxy_authorizes_only_exact_model(self) -> None:
        selector = "openai-codex/gpt-5.6-sol:max"
        exact = json.dumps({"model": "gpt-5.6-sol"}).encode("utf-8")
        neighbor = json.dumps({"model": "gpt-5.6-luna"}).encode("utf-8")

        self.assertEqual(
            "allow",
            gateway_socket_proxy.authorize_http_model_request(
                "POST", "/v1/responses", exact, selector
            )[0],
        )
        self.assertEqual(
            "deny",
            gateway_socket_proxy.authorize_http_model_request(
                "POST", "/v1/responses", neighbor, selector
            )[0],
        )
        self.assertEqual(
            "listing",
            gateway_socket_proxy.authorize_http_model_request("GET", "/v1/models", b"", selector)[0],
        )
        self.assertEqual(
            "deny",
            gateway_socket_proxy.authorize_http_model_request("GET", "/health", b"", selector)[0],
        )
        self.assertTrue(
            gateway_socket_proxy._model_listing_response(selector).startswith(b"HTTP/1.1 200 OK\r\n")
        )

    def test_gateway_socket_proxy_rejects_ambiguous_request_framing(self) -> None:
        import socket

        selector = "openai-codex/gpt-5.6-sol:max"
        body = json.dumps({"model": "gpt-5.6-sol"}, separators=(",", ":")).encode("utf-8")
        requests = [
            (
                b"Transfer-Encoding: identity\r\n"
                + f"Content-Length: {len(body)}\r\n".encode("ascii"),
                "Transfer-Encoding",
            ),
            (f"Content-Length: +{len(body)}\r\n".encode("ascii"), "Content-Length"),
        ]
        for framing_headers, expected_error in requests:
            with self.subTest(expected_error=expected_error):
                client, incoming = socket.socketpair()
                try:
                    client.sendall(
                        b"POST /v1/responses HTTP/1.1\r\n"
                        b"Host: gateway\r\n"
                        + framing_headers
                        + b"\r\n"
                        + body
                    )
                    client.shutdown(socket.SHUT_WR)
                    with self.assertRaisesRegex(ValueError, expected_error):
                        gateway_socket_proxy._read_http_request(incoming, selector)
                finally:
                    client.close()
                    incoming.close()

    def test_gateway_socket_proxy_denies_before_forwarding(self) -> None:
        import socket
        import threading

        selector = "openai-codex/gpt-5.6-sol:max"
        body = json.dumps({"model": "gpt-5.6-luna"}, separators=(",", ":")).encode("utf-8")
        request = (
            b"POST /v1/responses HTTP/1.1\r\n"
            b"Host: gateway\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"\r\n"
            + body
        )
        client, incoming = socket.socketpair()
        outgoing, backend = socket.socketpair()
        worker = threading.Thread(
            target=gateway_socket_proxy._serve_connection,
            args=(incoming, outgoing, selector),
            daemon=True,
        )
        worker.start()
        try:
            client.sendall(request)
            client.shutdown(socket.SHUT_WR)
            response = client.recv(4096)
            backend.settimeout(1)
            forwarded = backend.recv(4096)
        finally:
            client.close()
            backend.close()
        worker.join(timeout=2)

        self.assertIn(b"403 Forbidden", response)
        self.assertEqual(b"", forwarded)
        self.assertFalse(worker.is_alive())

    def test_gateway_socket_proxy_forwards_one_authorized_request(self) -> None:
        import socket
        import threading

        selector = "openai-codex/gpt-5.6-sol:max"

        def request_for(model: str) -> bytes:
            body = json.dumps({"model": model}, separators=(",", ":")).encode("utf-8")
            return (
                b"POST /v1/responses HTTP/1.1\r\n"
                b"Host: gateway\r\n"
                + f"Content-Length: {len(body)}\r\n".encode("ascii")
                + b"\r\n"
                + body
            )

        allowed = request_for("gpt-5.6-sol")
        pipelined_neighbor = request_for("gpt-5.6-luna")
        response = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"
        client, incoming = socket.socketpair()
        outgoing, backend = socket.socketpair()
        observed = bytearray()

        def backend_once() -> None:
            while True:
                chunk = backend.recv(4096)
                if not chunk:
                    break
                observed.extend(chunk)
            backend.sendall(response)
            backend.close()

        backend_worker = threading.Thread(target=backend_once, daemon=True)
        proxy_worker = threading.Thread(
            target=gateway_socket_proxy._serve_connection,
            args=(incoming, outgoing, selector),
            daemon=True,
        )
        backend_worker.start()
        proxy_worker.start()
        try:
            client.sendall(allowed + pipelined_neighbor)
            client.shutdown(socket.SHUT_WR)
            received = bytearray()
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                received.extend(chunk)
        finally:
            client.close()
        proxy_worker.join(timeout=2)
        backend_worker.join(timeout=2)

        self.assertEqual(allowed, bytes(observed))
        self.assertEqual(response, bytes(received))
        self.assertFalse(proxy_worker.is_alive())
        self.assertFalse(backend_worker.is_alive())

    def test_auth_gateway_socket_readiness_fails_dead_proxy(self) -> None:
        class DeadProxy:
            def poll(self) -> int:
                return 17

        with tempfile.TemporaryDirectory() as tmp:
            ready, reason = auth_gateway.wait_for_unix_socket(DeadProxy(), Path(tmp) / "gateway.sock")
        self.assertFalse(ready)
        self.assertIn("exited", reason)
        self.assertLessEqual(len(reason), 240)

    def test_auth_gateway_socket_readiness_fails_missing_socket(self) -> None:
        class LiveProxy:
            def poll(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmp:
            ready, reason = auth_gateway.wait_for_unix_socket(
                LiveProxy(),
                Path(tmp) / "gateway.sock",
                timeout_sec=0.01,
            )
        self.assertFalse(ready)
        self.assertIn("timed out", reason)
        self.assertLessEqual(len(reason), 240)

    def test_gateway_socket_proxy_run_tcp_lifecycle_and_signal(self) -> None:
        import socket
        import threading
        import time

        selector = "openai-codex/gpt-5.6-sol:max"
        tmp = Path(tempfile.mkdtemp())
        backend = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        unix_path = tmp / "gateway.sock"
        backend.bind(str(unix_path))
        backend.listen(2)
        listen_probe = socket.socket()
        listen_probe.bind(("127.0.0.1", 0))
        tcp_port = listen_probe.getsockname()[1]
        listen_probe.close()
        body = json.dumps({"model": "gpt-5.6-sol"}, separators=(",", ":")).encode("utf-8")
        request = (
            b"POST /v1/responses HTTP/1.1\r\n"
            b"Host: gateway\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"\r\n"
            + body
        )
        response = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"

        def backend_once() -> None:
            conn, _ = backend.accept()
            while conn.recv(4096):
                pass
            conn.sendall(response)
            conn.close()
            backend.close()

        threading.Thread(target=backend_once, daemon=True).start()
        proc = subprocess.Popen(
            [
                sys.executable,
                str(GATEWAY_SOCKET_MODULE_PATH),
                "run-tcp",
                "--socket",
                str(unix_path),
                "--listen",
                f"127.0.0.1:{tcp_port}",
                "--model-selector",
                selector,
                "--",
                "sleep",
                "30",
            ]
        )
        try:
            client = None
            for _ in range(100):
                try:
                    client = socket.create_connection(("127.0.0.1", tcp_port), timeout=0.1)
                    break
                except OSError:
                    time.sleep(0.02)
            self.assertIsNotNone(client)
            assert client is not None
            client.sendall(request)
            client.shutdown(socket.SHUT_WR)
            received = bytearray()
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                received.extend(chunk)
            self.assertEqual(response, bytes(received))
            client.close()
            proc.terminate()
            proc.wait(timeout=5)
            self.assertIsNotNone(proc.returncode)
            with self.assertRaises(OSError):
                socket.create_connection(("127.0.0.1", tcp_port), timeout=0.2)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)
            backend.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_gateway_stop_run_verifies_pids(self) -> None:
        import json
        import tempfile

        spec = importlib.util.spec_from_file_location("auth_gateway", AUTH_MODULE_PATH)
        assert spec is not None and spec.loader is not None
        auth = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = auth
        spec.loader.exec_module(auth)
        tmp_root = Path(tempfile.mkdtemp())
        try:
            auth.AUTH_ARTIFACT_ROOT = tmp_root
            proc = subprocess.Popen(["sleep", "30"])
            out_dir = tmp_root / "r"
            gen_dir = out_dir / "generation-1"
            gen_dir.mkdir(parents=True)
            status = {
                "run_id": "r",
                "generation": 1,
                "generation_dir": str(gen_dir),
                "broker_pid": proc.pid,
                "broker_cmd": ["sleep", "30"],
                "run_state": "running",
            }
            (out_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            (gen_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            code, stopped = auth.stop_run("r")
            self.assertEqual(code, 0)
            self.assertEqual(stopped["run_state"], "stopped")
            self.assertIsNotNone(proc.poll())
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    def test_gateway_restart_stopped_run_at_generation_two(self) -> None:
        import json
        import tempfile

        spec = importlib.util.spec_from_file_location("auth_gateway", AUTH_MODULE_PATH)
        assert spec is not None and spec.loader is not None
        auth = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = auth
        spec.loader.exec_module(auth)
        tmp_root = Path(tempfile.mkdtemp())
        try:
            auth.AUTH_ARTIFACT_ROOT = tmp_root
            out_dir = tmp_root / "r"
            gen_dir = out_dir / "generation-1"
            gen_dir.mkdir(parents=True)
            status = {
                "run_id": "r",
                "generation": 1,
                "generation_dir": str(gen_dir),
                "run_state": "stopped",
                "stopped": True,
            }
            (out_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            self.assertIsNone(auth._restart_error(status))
            self.assertEqual(auth._generation_number(out_dir) + 1, 2)
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    def test_gateway_live_generation_refuses_restart(self) -> None:
        import json
        import tempfile

        spec = importlib.util.spec_from_file_location("auth_gateway", AUTH_MODULE_PATH)
        assert spec is not None and spec.loader is not None
        auth = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = auth
        spec.loader.exec_module(auth)
        tmp_root = Path(tempfile.mkdtemp())
        proc: subprocess.Popen[str] | None = None
        try:
            auth.AUTH_ARTIFACT_ROOT = tmp_root
            proc = subprocess.Popen(["sleep", "30"])
            out_dir = tmp_root / "r"
            gen_dir = out_dir / "generation-1"
            gen_dir.mkdir(parents=True)
            status = {
                "run_id": "r",
                "generation": 1,
                "generation_dir": str(gen_dir),
                "broker_pid": proc.pid,
                "broker_cmd": ["sleep", "30"],
                "run_state": "running",
            }
            (out_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            deadline = time.monotonic() + 2
            while not auth._live_generation_pids(status) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(bool(auth._live_generation_pids(status)))
            self.assertEqual(auth._restart_error(status), "verified live generation refuses restart")
            proc.terminate()
            proc.wait(timeout=3)
            self.assertEqual(auth._restart_error(status), "prior generation must be explicitly stopped before restart")
        finally:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)
            shutil.rmtree(tmp_root, ignore_errors=True)
