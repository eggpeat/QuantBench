from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))


def load_candidate():
    path = WORKSPACE / "ode.py"
    spec = importlib.util.spec_from_file_location("candidate_ode", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_cli_fixture():
    subprocess.run([sys.executable, str(WORKSPACE / "run_ode.py")], cwd=WORKSPACE, check=True)
    report = json.loads((WORKSPACE / "outputs" / "ode_report.json").read_text(encoding="utf-8"))
    assert report["seed"] == 100
    exp = next(r for r in report["results"] if r["name"] == "exponential_decay")
    np.testing.assert_allclose(exp["final_y"], [np.exp(-exp["final_t"])], rtol=1e-5, atol=1e-8)
    osc = next(r for r in report["results"] if r["name"] == "damped_oscillator_event")
    assert osc["status"] == "event"
    assert len(osc["t_events"][0]) == 1


def test_exponential_decay_matches_analytic():
    mod = load_candidate()
    y0 = np.array([1.0])
    result = mod.integrate_rk45(lambda t, y: -y, (0.0, 3.0), y0, rtol=1e-8, atol=1e-10)
    assert result.status == "finished"
    np.testing.assert_allclose(result.y[:, -1], np.exp(-result.t[-1:]), rtol=1e-6, atol=1e-9)


def test_harmonic_oscillator_energy_decay():
    mod = load_candidate()

    def rhs(t, y):
        return np.array([y[1], -y[0]])

    y0 = np.array([1.0, 0.0])
    result = mod.integrate_rk45(rhs, (0.0, 4.0 * np.pi), y0, rtol=1e-8, atol=1e-10)
    assert result.status == "finished"
    np.testing.assert_allclose(result.y[:, -1], y0, rtol=1e-5, atol=1e-8)


def test_forward_and_reverse_integration():
    mod = load_candidate()
    y0 = np.array([0.0])

    def rhs(t, y):
        return np.array([np.cos(t)])

    forward = mod.integrate_rk45(rhs, (0.0, np.pi), y0)
    backward = mod.integrate_rk45(rhs, (np.pi, 0.0), forward.y[:, -1])
    assert forward.status == "finished"
    assert backward.status == "finished"
    np.testing.assert_allclose(backward.y[:, -1], y0, rtol=1e-6, atol=1e-6)


def test_terminal_event_stops_integration():
    mod = load_candidate()

    def event(t, y):
        return float(y[0] - 0.5)

    event.terminal = True
    event.direction = -1

    result = mod.integrate_rk45(lambda t, y: -y, (0.0, 5.0), np.array([1.0]), events=[event])
    assert result.status == "event"
    assert len(result.t_events[0]) == 1
    np.testing.assert_allclose(result.t_events[0][0], np.log(2.0), rtol=1e-4, atol=1e-6)


def test_directional_event_only_counts_matching_crossings():
    mod = load_candidate()

    def event(t, y):
        return float(np.sin(t))

    event.terminal = False
    event.direction = 1  # only negative-to-positive crossings

    result = mod.integrate_rk45(
        lambda t, y: np.ones(1), (0.1, 4.0 * np.pi), np.zeros(1), events=[event], max_step=2.0
    )
    assert result.status == "finished"
    # sin(t) crosses upward at 2*pi within (0.1, 4*pi).
    np.testing.assert_allclose(result.t_events[0], [2.0 * np.pi], rtol=1e-6, atol=1e-8)


def test_stiff_problem_fails_cleanly():
    mod = load_candidate()
    # y' = y^2 with y(0)=1 has a finite-time blow-up at t=1. The adaptive
    # solver must fail clearly (step underflow) rather than hang.
    result = mod.integrate_rk45(lambda t, y: y * y, (0.0, 2.0), np.array([1.0]), rtol=1e-6, atol=1e-9)
    assert result.status == "failed"
    assert result.n_steps + result.n_rejected > 0
    assert "underflow" in result.message.lower() or "step" in result.message.lower()


def test_tolerance_scaling_improves_accuracy():
    mod = load_candidate()
    y0 = np.array([1.0])
    loose = mod.integrate_rk45(lambda t, y: -y, (0.0, 2.0), y0, rtol=1e-3, atol=1e-6)
    tight = mod.integrate_rk45(lambda t, y: -y, (0.0, 2.0), y0, rtol=1e-10, atol=1e-12)
    loose_err = abs(loose.y[0, -1] - np.exp(-loose.t[-1]))
    tight_err = abs(tight.y[0, -1] - np.exp(-tight.t[-1]))
    assert tight_err < loose_err


def test_vector_state_shape():
    mod = load_candidate()

    def rhs(t, y):
        return np.array([-y[0], y[1]])

    result = mod.integrate_rk45(rhs, (0.0, 1.0), np.array([1.0, 2.0]))
    assert result.status == "finished"
    assert result.y.shape == (2, len(result.t))


def test_discontinuous_event_boundary():
    mod = load_candidate()

    def event(t, y):
        return float(t - 1.0)

    event.terminal = True
    event.direction = 1

    result = mod.integrate_rk45(lambda t, y: np.ones(1), (0.0, 3.0), np.zeros(1), events=[event])
    assert result.status == "event"
    np.testing.assert_allclose(result.t_events[0][0], 1.0, rtol=1e-6, atol=1e-8)
