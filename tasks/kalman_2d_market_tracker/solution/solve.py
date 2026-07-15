"""Oracle solution for the Kalman 2D market tracker task."""

from __future__ import annotations
import sys
from pathlib import Path

SOLVED_SOURCE = '''"""Multivariate 2D Kalman filter for market price tracking and anomaly detection."""

from __future__ import annotations
import math

def matmul(A, B):
    if not isinstance(B[0], list):
        res = []
        for i in range(len(A)):
            s = 0.0
            for j in range(len(A[0])):
                s += A[i][j] * B[j]
            res.append(s)
        return res
    else:
        res = [[0.0] * len(B[0]) for _ in range(len(A))]
        for i in range(len(A)):
            for j in range(len(B[0])):
                s = 0.0
                for k in range(len(A[0])):
                    s += A[i][k] * B[k][j]
                res[i][j] = s
        return res

def transpose(A):
    if not isinstance(A[0], list):
        return [A]
    return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]

def matadd(A, B):
    if not isinstance(A[0], list):
        return [a + b for a, b in zip(A, B)]
    return [[A[i][j] + B[i][j] for j in range(len(A[0]))] for i in range(len(A))]

def matsub(A, B):
    if not isinstance(A[0], list):
        return [a - b for a, b in zip(A, B)]
    return [[A[i][j] - B[i][j] for j in range(len(A[0]))] for i in range(len(A))]

def matscalar(A, s):
    if not isinstance(A[0], list):
        return [a * s for a in A]
    return [[A[i][j] * s for j in range(len(A[0]))] for i in range(len(A))]

def matinv(A):
    M = len(A)
    if M == 1:
        det = A[0][0]
        if abs(det) < 1e-12 or det <= 0:
            raise ValueError("Matrix is singular or not positive-definite")
        return [[1.0 / det]]
    elif M == 2:
        a, b = A[0][0], A[0][1]
        c, d = A[1][0], A[1][1]
        det = a * d - b * c
        if abs(det) < 1e-12:
            raise ValueError("Matrix is singular")
        inv_det = 1.0 / det
        return [
            [d * inv_det, -b * inv_det],
            [-c * inv_det, a * inv_det]
        ]
    else:
        raise NotImplementedError("Only 1x1 and 2x2 matrix inversion supported")


def predict(
    x: list[float],
    P: list[list[float]],
    F: list[list[float]],
    Q: list[list[float]],
) -> tuple[list[float], list[list[float]]]:
    """Perform the Kalman filter prediction step."""
    if P[0][0] < 0 or P[1][1] < 0:
        raise ValueError("Covariance matrix diagonals cannot be negative")
    if Q[0][0] < 0 or Q[1][1] < 0:
        raise ValueError("Process noise diagonals cannot be negative")

    x_pred = matmul(F, x)
    P_pred = matadd(matmul(matmul(F, P), transpose(F)), Q)
    return x_pred, P_pred


def update(
    x_pred: list[float],
    P_pred: list[list[float]],
    z: list[float],
    H: list[list[float]],
    R: list[list[float]],
    anomaly_threshold: float,
    inflation_factor: float,
) -> tuple[list[float], list[list[float]], bool, float]:
    """Perform the Kalman filter measurement update step with covariance inflation."""
    for i in range(len(R)):
        if R[i][i] < 0:
            raise ValueError("Measurement noise diagonals cannot be negative")
    if anomaly_threshold < 0:
        raise ValueError("Anomaly threshold cannot be negative")
    if inflation_factor < 0:
        raise ValueError("Inflation factor cannot be negative")

    y = matsub(z, matmul(H, x_pred))
    S = matadd(matmul(matmul(H, P_pred), transpose(H)), R)
    S_inv = matinv(S)

    d_m_sq = sum(a * b for a, b in zip(y, matmul(S_inv, y)))
    mahalanobis = math.sqrt(max(0.0, d_m_sq))

    anomaly = mahalanobis > anomaly_threshold

    if anomaly:
        P_pred = matscalar(P_pred, inflation_factor)
        S = matadd(matmul(matmul(H, P_pred), transpose(H)), R)
        S_inv = matinv(S)

    K = matmul(matmul(P_pred, transpose(H)), S_inv)
    x_opt = matadd(x_pred, matmul(K, y))
    P_opt = matsub(P_pred, matmul(matmul(K, H), P_pred))

    return x_opt, P_opt, anomaly, mahalanobis


def filter_series(rows: list[dict], config: dict) -> dict:
    """Run the Kalman filter sequentially over rows of price observations."""
    x = config["initial_state"]
    P = config["initial_covariance"]
    F = config["transition_matrix"]
    Q = config["process_noise"]
    H = config["measurement_matrix"]
    R = config["measurement_noise"]
    anomaly_threshold = config["anomaly_threshold"]
    inflation_factor = config["inflation_factor"]

    steps = []
    for obs in rows:
        z = [obs["price"]]
        x_pred, P_pred = predict(x, P, F, Q)
        x, P, anomaly, mahalanobis = update(
            x_pred, P_pred, z, H, R, anomaly_threshold, inflation_factor
        )
        steps.append({
            "time": obs["time"],
            "state": x,
            "covariance": P,
            "anomaly": anomaly,
            "mahalanobis": mahalanobis
        })

    return {
        "steps": steps,
        "final_state": x,
        "final_covariance": P
    }
'''

def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    (workspace / "kalman2d.py").write_text(SOLVED_SOURCE, encoding="utf-8")

    # Run the filtering script
    sys.path.insert(0, str(workspace))
    import run_kalman2d
    run_kalman2d.main()

if __name__ == "__main__":
    main()
