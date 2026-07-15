#!/usr/bin/env python3
"""Standard-library OMP JSONL capture and runtime metric helpers."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable


RUNTIME_METRIC_VERSION = "runtime_metrics_v2_omp_usage_capture"
RUNTIME_METRIC_KEYS = (
    "source",
    "latency",
    "tokens",
    "cache",
    "throughput",
    "provider_route",
    "notes",
)
RUNTIME_USAGE_PREFIXES = ("OMP_USAGE_JSON=", "OMP_RUNTIME_METRICS=")
THINKING_SUFFIXES = ("minimal", "low", "medium", "high", "xhigh", "max", "none", "off", "auto", "raw")
OMP_JSONL_MAX_LINE_BYTES = 1024 * 1024
OMP_JSONL_TAIL_BYTES = 64 * 1024


def estimate_visible_tokens(text: str) -> int:
    if not text.strip():
        return 0
    return max(1, round(len(text) / 4))


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = float(stripped)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def token_count(*values: Any) -> int | None:
    for value in values:
        number = finite_number(value)
        if number is not None and number >= 0:
            return int(number)
    return None


def nested_value(mapping: dict[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def split_model_ref(model: str) -> tuple[str, str | None]:
    base, sep, suffix = model.rpartition(":")
    if sep and suffix in THINKING_SUFFIXES and base:
        return base, suffix
    return model, None


def model_provider(model: str) -> str | None:
    provider, sep, _rest = model.partition("/")
    return provider if sep and provider else None


def model_base(model: str) -> str:
    base, _thinking = split_model_ref(model)
    return base


def gateway_model_id(model: str) -> str:
    base = model_base(model)
    _provider, sep, rest = base.partition("/")
    return rest if sep else base


def usage_from_metric_line(text: str) -> dict[str, Any] | None:
    for line in text.splitlines():
        stripped = line.strip()
        for prefix in RUNTIME_USAGE_PREFIXES:
            if not stripped.startswith(prefix):
                continue
            try:
                parsed = json.loads(stripped[len(prefix) :])
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


def usage_payload_from_run(run: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    for key, source in (
        ("provider_usage", "provider_usage"),
        ("proxy_usage", "proxy_usage"),
    ):
        value = run.get(key)
        if isinstance(value, dict):
            return value, source
    stderr_usage = usage_from_metric_line(str(run.get("stderr") or ""))
    if stderr_usage is not None:
        return stderr_usage, "proxy_usage" if str(stderr_usage.get("source") or "").startswith("proxy") else "provider_usage"
    value = run.get("usage")
    if isinstance(value, dict):
        return value, "provider_usage"
    return None, None


def text_from_omp_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(part for part in parts if part)


def omp_message_usage_payload(message: dict[str, Any]) -> dict[str, Any] | None:
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    input_new = token_count(usage.get("input"))
    cache_read = token_count(usage.get("cacheRead"))
    cache_write = token_count(usage.get("cacheWrite"))
    output = token_count(usage.get("output"))
    total = token_count(usage.get("totalTokens"))
    reasoning = token_count(usage.get("reasoningTokens"))
    duration_ms = token_count(message.get("duration"))
    ttft_ms = token_count(message.get("ttft"))
    generation_ms = None
    if duration_ms is not None:
        generation_ms = max(0, duration_ms - ttft_ms) if ttft_ms is not None else duration_ms

    payload: dict[str, Any] = {}
    if input_new is not None or cache_read is not None or cache_write is not None:
        payload["input_tokens"] = (input_new or 0) + (cache_read or 0) + (cache_write or 0)
    if output is not None:
        payload["output_tokens"] = output
    if total is not None:
        payload["total_tokens"] = total
    if reasoning is not None:
        payload["reasoning_output_tokens"] = reasoning
    if cache_read is not None:
        payload["cached_input_tokens"] = cache_read
    if cache_write is not None:
        payload["cache_write_input_tokens"] = cache_write
    if ttft_ms is not None:
        payload["ttft_ms"] = ttft_ms
    if generation_ms is not None:
        payload["generation_ms"] = generation_ms
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    for key in ("provider", "api", "model"):
        value = message.get(key)
        if isinstance(value, str) and value:
            payload[key] = value
    return payload


def sum_known(payloads: list[dict[str, Any]], key: str) -> int | None:
    values = [value for payload in payloads if (value := token_count(payload.get(key))) is not None]
    return sum(values) if values else None


def average_known(payloads: list[dict[str, Any]], key: str) -> int | None:
    values = [value for payload in payloads if (value := token_count(payload.get(key))) is not None]
    return round(sum(values) / len(values)) if values else None


def first_stable_string(payloads: list[dict[str, Any]], key: str) -> str | None:
    values = [str(payload[key]) for payload in payloads if isinstance(payload.get(key), str) and payload.get(key)]
    return values[0] if values and all(value == values[0] for value in values) else None


def assistant_messages_from_omp_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    message_end_assistants = [
        message
        for event in events
        if event.get("type") == "message_end"
        and isinstance((message := event.get("message")), dict)
        and message.get("role") == "assistant"
    ]
    agent_end_assistants: list[dict[str, Any]] = []
    for event in reversed(events):
        messages = event.get("messages")
        if event.get("type") != "agent_end" or not isinstance(messages, list):
            continue
        agent_end_assistants = [
            message
            for message in messages
            if isinstance(message, dict) and message.get("role") == "assistant"
        ]
        break

    if agent_end_assistants and agent_end_assistants[-1].get("stopReason") in {"error", "aborted"}:
        return agent_end_assistants
    if message_end_assistants:
        return message_end_assistants
    return agent_end_assistants


_OMP_USAGE_SUM_KEYS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "reasoning_output_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "generation_ms",
    "duration_ms",
)


def _accumulate_omp_usage(state: dict[str, Any], message: dict[str, Any]) -> None:
    payload = omp_message_usage_payload(message)
    if payload is None:
        return
    state["turns"] = int(state.get("turns", 0)) + 1
    for key in _OMP_USAGE_SUM_KEYS:
        value = token_count(payload.get(key))
        if value is not None:
            state[key] = int(state.get(key, 0)) + value
    ttft_ms = token_count(payload.get("ttft_ms"))
    if ttft_ms is not None:
        state["ttft_sum"] = int(state.get("ttft_sum", 0)) + ttft_ms
        state["ttft_count"] = int(state.get("ttft_count", 0)) + 1
    for key in ("provider", "api", "model"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            continue
        state_key = f"{key}_value"
        if state_key not in state:
            state[state_key] = value
        elif state[state_key] != value:
            state[f"{key}_mixed"] = True


def _finalize_omp_usage(state: dict[str, Any]) -> dict[str, Any] | None:
    turns = int(state.get("turns", 0))
    if not turns:
        return None
    aggregate: dict[str, Any] = {"omp_assistant_turns": turns}
    for key in _OMP_USAGE_SUM_KEYS:
        if key in state:
            aggregate[key] = state[key]
    if state.get("ttft_count"):
        aggregate["ttft_ms"] = round(state["ttft_sum"] / state["ttft_count"])
    for key in ("provider", "api", "model"):
        if not state.get(f"{key}_mixed") and f"{key}_value" in state:
            aggregate[key] = state[f"{key}_value"]
    return aggregate


def iter_omp_jsonl_file(path: Path) -> Iterable[str]:
    """Yield bounded JSONL records, summarizing transcript-heavy agent_end lines."""
    with path.open("rb") as handle:
        while True:
            chunk = handle.readline(OMP_JSONL_MAX_LINE_BYTES + 1)
            if not chunk:
                return
            if len(chunk) <= OMP_JSONL_MAX_LINE_BYTES:
                yield chunk.decode("utf-8", errors="replace")
                continue
            prefix = chunk[:4096]
            tail = chunk[-OMP_JSONL_TAIL_BYTES:]
            while not chunk.endswith(b"\n"):
                chunk = handle.readline(OMP_JSONL_MAX_LINE_BYTES + 1)
                if not chunk:
                    break
                tail = (tail + chunk)[-OMP_JSONL_TAIL_BYTES:]
            if b'"agent_end"' not in prefix:
                yield json.dumps({
                    "type": "oversize_json_event",
                    "errorMessage": "OMP JSON event exceeded the bounded parser limit",
                })
                continue
            stop_reasons = re.findall(rb'"stopReason"\s*:\s*"([^"]+)"', tail)
            stop_reason = stop_reasons[-1].decode("utf-8", errors="replace") if stop_reasons else ""
            terminal_failure = stop_reason if stop_reason in {"error", "failed", "aborted"} else ""
            yield json.dumps({
                "type": "agent_end_oversize",
                "stopReason": terminal_failure,
                "errorMessage": (
                    f"Oversized agent_end terminated with {terminal_failure}"
                    if terminal_failure
                    else ""
                ),
            })


def _capture_omp_json_lines(run: dict[str, Any], lines: Iterable[str]) -> None:
    message_final: dict[str, Any] | None = None
    message_usage: dict[str, Any] = {}
    agent_final: dict[str, Any] | None = None
    agent_usage: dict[str, Any] = {}
    event_count = 0
    parse_errors = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type == "agent_end_oversize":
            stop_reason = event.get("stopReason")
            if stop_reason in {"error", "failed", "aborted"}:
                agent_final = {
                    "role": "assistant",
                    "content": "",
                    "stopReason": stop_reason,
                    "errorMessage": event.get("errorMessage"),
                }
            event_count += 1
            continue
        if event_type == "oversize_json_event":
            agent_final = {
                "role": "assistant",
                "content": "",
                "stopReason": "error",
                "errorMessage": event.get("errorMessage"),
            }
            event_count += 1
            continue
        event_count += 1
        message = event.get("message")
        if (
            event.get("type") == "message_end"
            and isinstance(message, dict)
            and message.get("role") == "assistant"
        ):
            _accumulate_omp_usage(message_usage, message)
            message_final = message
        messages = event.get("messages")
        if event.get("type") == "agent_end" and isinstance(messages, list):
            current_usage: dict[str, Any] = {}
            current_final: dict[str, Any] | None = None
            for item in messages:
                if isinstance(item, dict) and item.get("role") == "assistant":
                    _accumulate_omp_usage(current_usage, item)
                    current_final = item
            agent_usage = current_usage
            agent_final = current_final

    use_agent = (
        agent_final is not None
        and agent_final.get("stopReason") in {"error", "aborted"}
    )
    final_message = agent_final if use_agent else message_final or agent_final
    usage_state = (
        agent_usage
        if use_agent and agent_usage
        else message_usage
        if message_final is not None
        else agent_usage
    )
    if event_count:
        run["omp_json_event_count"] = event_count
    if parse_errors:
        run["omp_json_parse_errors"] = parse_errors
    if final_message is None:
        return

    run["stdout"] = text_from_omp_content(final_message.get("content"))
    usage = _finalize_omp_usage(usage_state)
    if usage is not None:
        run["omp_assistant_message_count"] = usage["omp_assistant_turns"]
        run["usage"] = usage

    stop_reason = final_message.get("stopReason")
    error_message = final_message.get("errorMessage")
    if isinstance(stop_reason, str):
        run["omp_stop_reason"] = stop_reason
    if stop_reason in {"error", "aborted"}:
        error_text = error_message if isinstance(error_message, str) and error_message else f"Request {stop_reason}"
        run["omp_error_message"] = error_text
        existing_stderr = str(run.get("stderr") or "").rstrip()
        run["stderr"] = (
            f"{existing_stderr}\n{error_text}"
            if existing_stderr and error_text not in existing_stderr
            else existing_stderr or error_text
        )
        if run.get("returncode") == 0:
            run["returncode"] = 1
    elif isinstance(error_message, str) and error_message:
        run["omp_error_message"] = error_message
        existing_stderr = str(run.get("stderr") or "").rstrip()
        run["stderr"] = (
            f"{existing_stderr}\n{error_message}"
            if existing_stderr and error_message not in existing_stderr
            else existing_stderr or error_message
        )


def capture_omp_json_stdout(run: dict[str, Any]) -> None:
    raw_stdout = str(run.get("stdout") or "")
    if raw_stdout.strip():
        _capture_omp_json_lines(run, raw_stdout.splitlines())


def capture_omp_json_file(run: dict[str, Any], path: Path) -> None:
    """Capture final OMP output and usage without loading the JSONL file."""
    _capture_omp_json_lines(run, iter_omp_jsonl_file(path))


def finalize_omp_run_capture(run: dict[str, Any]) -> dict[str, Any]:
    capture_omp_json_stdout(run)
    return run


def response_cache_hit_from_usage(usage: dict[str, Any], run: dict[str, Any]) -> bool | None:
    for value in (
        run.get("response_cache_hit"),
        usage.get("response_cache_hit"),
        usage.get("responseCacheHit"),
        usage.get("proxy_response_cache_hit"),
        usage.get("proxyCacheHit"),
    ):
        if isinstance(value, bool):
            return value
    return None


def normalized_usage_tokens(usage: dict[str, Any]) -> dict[str, int | None]:
    input_tokens = token_count(
        usage.get("input_tokens"),
        usage.get("prompt_tokens"),
        usage.get("inputTokens"),
        usage.get("promptTokenCount"),
        nested_value(usage, "usageMetadata", "promptTokenCount"),
        nested_value(usage, "usage_metadata", "prompt_token_count"),
    )
    output_tokens = token_count(
        usage.get("output_tokens"),
        usage.get("completion_tokens"),
        usage.get("outputTokens"),
        usage.get("candidatesTokenCount"),
        nested_value(usage, "usageMetadata", "candidatesTokenCount"),
        nested_value(usage, "usage_metadata", "candidates_token_count"),
    )
    reasoning_tokens = token_count(
        usage.get("reasoning_output_tokens"),
        usage.get("reasoning_tokens"),
        nested_value(usage, "output_tokens_details", "reasoning_tokens"),
        nested_value(usage, "completion_tokens_details", "reasoning_tokens"),
        nested_value(usage, "usageMetadata", "thoughtsTokenCount"),
        nested_value(usage, "usage_metadata", "thoughts_token_count"),
    )
    cached_input_tokens = token_count(
        usage.get("cached_input_tokens"),
        usage.get("input_cached_tokens"),
        usage.get("cache_read_input_tokens"),
        nested_value(usage, "input_tokens_details", "cached_tokens"),
        nested_value(usage, "prompt_tokens_details", "cached_tokens"),
        nested_value(usage, "usageMetadata", "cachedContentTokenCount"),
        nested_value(usage, "usage_metadata", "cached_content_token_count"),
    )
    cache_write_input_tokens = token_count(
        usage.get("cache_write_input_tokens"),
        usage.get("input_cache_write_tokens"),
        usage.get("cache_creation_input_tokens"),
    )
    if "cache_read_input_tokens" in usage or "cache_creation_input_tokens" in usage:
        input_tokens = (
            (input_tokens or 0)
            + (cached_input_tokens or 0)
            + (cache_write_input_tokens or 0)
        )
    total_tokens = token_count(
        usage.get("total_tokens"),
        usage.get("totalTokens"),
        usage.get("totalTokenCount"),
        nested_value(usage, "usageMetadata", "totalTokenCount"),
        nested_value(usage, "usage_metadata", "total_token_count"),
    )
    if input_tokens is not None and output_tokens is not None:
        provider_total = total_tokens
        total_tokens = input_tokens + output_tokens
        if provider_total is not None and provider_total >= total_tokens:
            total_tokens = provider_total
    return {
        "input": input_tokens,
        "output": output_tokens,
        "reasoning_output": reasoning_tokens,
        "total": total_tokens,
        "cached_input": cached_input_tokens,
        "cache_write_input": cache_write_input_tokens,
    }


def runtime_cache_metrics(
    usage: dict[str, Any],
    run: dict[str, Any],
    tokens: dict[str, int | None],
) -> dict[str, Any]:
    cached_input = tokens["cached_input"]
    cache_write = tokens["cache_write_input"]
    input_tokens = tokens["input"]
    input_uncached = None
    cache_read_ratio = None
    if input_tokens is not None and cached_input is not None:
        input_uncached = max(0, input_tokens - cached_input)
        if input_tokens > 0:
            cache_read_ratio = round(cached_input / input_tokens, 4)
    return {
        "supported": cached_input is not None or cache_write is not None,
        "prompt_cache_hit": (cached_input > 0) if cached_input is not None else None,
        "input_cached": cached_input,
        "input_cache_write": cache_write,
        "input_uncached": input_uncached,
        "input_total": input_tokens,
        "cache_read_ratio": cache_read_ratio,
        "response_cache_hit": response_cache_hit_from_usage(usage, run),
    }


def runtime_provider_route(
    model: str | None,
    usage: dict[str, Any],
    auth_gateway_url: str | None,
) -> dict[str, Any]:
    base = model_base(model) if model else None
    provider = model_provider(base) if base else None
    return {
        "provider": provider,
        "base_model": base,
        "model_id": gateway_model_id(model) if model else None,
        "auth_gateway": bool(auth_gateway_url),
        "service_tier": usage.get("service_tier") or usage.get("serviceTier"),
        "region": usage.get("region") or usage.get("provider_region") or usage.get("providerRegion"),
    }


def runtime_metrics_for_run(
    run: dict[str, Any],
    *,
    model: str | None = None,
    auth_gateway_url: str | None = None,
) -> dict[str, Any]:
    usage, usage_source = usage_payload_from_run(run)
    usage = usage or {}
    tokens = normalized_usage_tokens(usage)
    output_chars = token_count(run.get("omp_stdout_char_count"))
    visible_output_tokens = (
        max(1, round(output_chars / 4))
        if output_chars is not None and output_chars > 0
        else estimate_visible_tokens(str(run.get("stdout") or ""))
    )
    elapsed_sec = finite_number(run.get("elapsed_sec"))
    wall_ms = round(elapsed_sec * 1000) if elapsed_sec is not None else None
    wall_seconds = elapsed_sec if elapsed_sec and elapsed_sec > 0 else None
    ttft_ms = token_count(usage.get("ttft_ms"), usage.get("time_to_first_token_ms"))
    generation_ms = token_count(usage.get("generation_ms"), usage.get("generationTimeMs"))
    generation_seconds = generation_ms / 1000 if generation_ms and generation_ms > 0 else None
    provider_ms = token_count(usage.get("duration_ms"), usage.get("durationMs"))
    provider_seconds = provider_ms / 1000 if provider_ms and provider_ms > 0 else None
    output_seconds = provider_seconds or generation_seconds
    output_tok_s = (
        round(tokens["output"] / output_seconds, 3)
        if output_seconds and tokens["output"] is not None
        else None
    )
    wall_output_tok_s = (
        round(tokens["output"] / wall_seconds, 3)
        if wall_seconds and tokens["output"] is not None
        else None
    )
    total_tok_s = (
        round(tokens["total"] / wall_seconds, 3)
        if wall_seconds and tokens["total"] is not None
        else None
    )
    visible_tok_s = round(visible_output_tokens / wall_seconds, 3) if wall_seconds else None
    source = usage_source or ("harness_estimate" if elapsed_sec is not None else "none")
    return {
        "source": source,
        "latency": {
            "wall_ms": wall_ms,
            "ttft_ms": ttft_ms,
            "generation_ms": generation_ms,
            "provider_ms": provider_ms,
        },
        "tokens": {
            "input": tokens["input"],
            "output": tokens["output"],
            "reasoning_output": tokens["reasoning_output"],
            "total": tokens["total"],
            "visible_output_est": visible_output_tokens,
        },
        "cache": runtime_cache_metrics(usage, run, tokens),
        "throughput": {
            "output_tok_s": output_tok_s,
            "wall_output_tok_s": wall_output_tok_s,
            "total_tok_s": total_tok_s,
            "visible_output_tok_s_est": visible_tok_s,
            "visible_post_ttft_tok_s_est": (
                round(visible_output_tokens / generation_seconds, 3) if generation_seconds else None
            ),
        },
        "provider_route": runtime_provider_route(model, usage, auth_gateway_url),
        "notes": {
            "metric_version": RUNTIME_METRIC_VERSION,
            "provider_usage": "OMP JSON message_end usage or provider/proxy metric lines when exposed; otherwise null.",
            "output_tok_s": "Provider output tokens divided by provider duration when exposed; falls back to generation_ms.",
            "visible_output_est": "Fallback estimate from final captured stdout length.",
            "response_cache_hit": "Tracked separately from provider prompt-cache reads.",
        },
    }


def metric_section_value(metrics: dict[str, Any], section: str, key: str) -> Any:
    nested = metrics.get(section)
    if not isinstance(nested, dict):
        return None
    return nested.get(key)


def metric_int_values(metric_rows: list[dict[str, Any]], section: str, key: str) -> list[int]:
    return [
        int(value)
        for metrics in metric_rows
        if (value := token_count(metric_section_value(metrics, section, key))) is not None
    ]


def sum_metric_values(
    metric_rows: list[dict[str, Any]],
    section: str,
    key: str,
    *,
    require_all: bool = False,
) -> int | None:
    values = metric_int_values(metric_rows, section, key)
    if not values or (require_all and len(values) != len(metric_rows)):
        return None
    return sum(values)


def metric_coverage(metric_rows: list[dict[str, Any]], section: str, key: str) -> dict[str, int]:
    return {
        "known": len(metric_int_values(metric_rows, section, key)),
        "total": len(metric_rows),
    }


def any_known_bool(values: list[Any]) -> bool | None:
    known = [value for value in values if isinstance(value, bool)]
    if not known:
        return None
    return any(known)


def runtime_metric_source(metric_rows: list[dict[str, Any]]) -> str:
    sources = {str(metrics.get("source")) for metrics in metric_rows if metrics.get("source")}
    if "provider_usage" in sources:
        return "provider_usage"
    if "proxy_usage" in sources:
        return "proxy_usage"
    if "harness_estimate" in sources:
        return "harness_estimate"
    return "none"


def runtime_route_summary(metric_rows: list[dict[str, Any]]) -> dict[str, Any]:
    routes = [metrics.get("provider_route") for metrics in metric_rows if isinstance(metrics.get("provider_route"), dict)]
    return {
        "providers": sorted({str(route["provider"]) for route in routes if route.get("provider")}),
        "base_models": sorted({str(route["base_model"]) for route in routes if route.get("base_model")}),
        "model_ids": sorted({str(route["model_id"]) for route in routes if route.get("model_id")}),
        "auth_gateway": any(bool(route.get("auth_gateway")) for route in routes),
        "service_tiers": sorted({str(route["service_tier"]) for route in routes if route.get("service_tier")}),
        "regions": sorted({str(route["region"]) for route in routes if route.get("region")}),
    }


def runtime_metrics_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gate_rows = [row for row in rows if not str(row.get("gate", "")).startswith("thinking_")]
    metric_rows = [
        row["runtime_metrics"]
        for row in gate_rows
        if isinstance(row.get("runtime_metrics"), dict)
    ]
    if not metric_rows:
        metric_rows = [
            runtime_metrics_for_run(row, model=str(row.get("model") or "") or None, auth_gateway_url=row.get("auth_gateway_url"))
            for row in gate_rows
        ]
    wall_ms = sum_metric_values(metric_rows, "latency", "wall_ms")
    ttft_values = [
        value
        for metrics in metric_rows
        if (value := token_count(metric_section_value(metrics, "latency", "ttft_ms"))) is not None
    ]
    ttft_ms = round(sum(ttft_values) / len(ttft_values)) if ttft_values else None
    generation_ms = sum_metric_values(metric_rows, "latency", "generation_ms")
    provider_ms = sum_metric_values(metric_rows, "latency", "provider_ms", require_all=True)
    input_tokens = sum_metric_values(metric_rows, "tokens", "input", require_all=True)
    output_tokens = sum_metric_values(metric_rows, "tokens", "output", require_all=True)
    reasoning_tokens = sum_metric_values(metric_rows, "tokens", "reasoning_output", require_all=True)
    total_tokens = sum_metric_values(metric_rows, "tokens", "total", require_all=True)
    visible_output_tokens = sum_metric_values(metric_rows, "tokens", "visible_output_est") or 0
    cached_input_tokens = sum_metric_values(metric_rows, "cache", "input_cached", require_all=True)
    cache_write_tokens = sum_metric_values(metric_rows, "cache", "input_cache_write", require_all=True)
    input_uncached = None
    cache_read_ratio = None
    if input_tokens is not None and cached_input_tokens is not None:
        input_uncached = max(0, input_tokens - cached_input_tokens)
        if input_tokens > 0:
            cache_read_ratio = round(cached_input_tokens / input_tokens, 4)
    wall_seconds = (wall_ms / 1000) if wall_ms and wall_ms > 0 else None
    generation_seconds = (generation_ms / 1000) if generation_ms and generation_ms > 0 else None
    output_seconds = (provider_ms / 1000) if provider_ms and provider_ms > 0 else generation_seconds
    response_cache_hit = any_known_bool(
        [metric_section_value(metrics, "cache", "response_cache_hit") for metrics in metric_rows]
    )
    return {
        "source": runtime_metric_source(metric_rows),
        "latency": {
            "wall_ms": wall_ms,
            "ttft_ms": ttft_ms,
            "generation_ms": generation_ms,
            "provider_ms": provider_ms,
        },
        "tokens": {
            "input": input_tokens,
            "output": output_tokens,
            "reasoning_output": reasoning_tokens,
            "total": total_tokens,
            "visible_output_est": visible_output_tokens,
        },
        "cache": {
            "supported": any(bool(metric_section_value(metrics, "cache", "supported")) for metrics in metric_rows),
            "prompt_cache_hit": any_known_bool(
                [metric_section_value(metrics, "cache", "prompt_cache_hit") for metrics in metric_rows]
            ),
            "input_cached": cached_input_tokens,
            "input_cache_write": cache_write_tokens,
            "input_uncached": input_uncached,
            "input_total": input_tokens,
            "cache_read_ratio": cache_read_ratio,
            "response_cache_hit": response_cache_hit,
        },
        "throughput": {
            "output_tok_s": (
                round(output_tokens / output_seconds, 3)
                if output_seconds and output_tokens is not None
                else None
            ),
            "wall_output_tok_s": (
                round(output_tokens / wall_seconds, 3) if wall_seconds and output_tokens is not None else None
            ),
            "total_tok_s": round(total_tokens / wall_seconds, 3) if wall_seconds and total_tokens is not None else None,
            "visible_output_tok_s_est": round(visible_output_tokens / wall_seconds, 3) if wall_seconds else None,
            "visible_post_ttft_tok_s_est": (
                round(visible_output_tokens / generation_seconds, 3) if generation_seconds else None
            ),
        },
        "provider_route": runtime_route_summary(metric_rows),
        "notes": {
            "metric_version": RUNTIME_METRIC_VERSION,
            "aggregation": "Sum only complete provider/proxy token coverage across current hardcoded gates; partial token totals stay null.",
            "coverage": {
                "gate_count": len(metric_rows),
                "input_tokens": metric_coverage(metric_rows, "tokens", "input"),
                "output_tokens": metric_coverage(metric_rows, "tokens", "output"),
                "total_tokens": metric_coverage(metric_rows, "tokens", "total"),
                "cached_input_tokens": metric_coverage(metric_rows, "cache", "input_cached"),
            },
            "capability_scoring": "Runtime metrics are reported only; they do not change pass/fail or layered scores.",
        },
    }
