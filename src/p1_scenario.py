# P1.0 - Synthetic single-scan tracking scenario, GNN cost matrix, Hungarian baseline.
#
# Textbook set-up, nothing operational:
#   - constant-velocity Kalman prediction of each track (discrete white-noise acceleration)
#   - position-only measurements with Gaussian noise, detection probability P_D
#   - clutter: Poisson number of false alarms, uniform in a window around the tracks
#   - chi-square gating on the innovation
#   - cost of assigning measurement j to track i = -ln( P_D * N(z_j; z_hat_i, S_i) / lambda )
#                                               = 1/2 d^2 + 1/2 ln|2 pi S| - ln(P_D / lambda)
#   - missed detection cost -ln(1 - P_D); a measurement declared clutter costs 0 (the reference)
#   - augmented (T + M) x (T + M) matrix so every row and column is assigned exactly once
#
# "Pure" mode (P_D = 1, no clutter, no gating) gives a plain T x T assignment, the size used later
# for small QAOA instances on hardware.
#
# Usage:
#     python src/p1_scenario.py                         # one example scene + a 500-scene baseline
#     python src/p1_scenario.py --targets 4 --scenes 1000 --seed 7
#     python src/p1_scenario.py --pure --targets 3

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import itertools
import json
import math
import pathlib

import numpy as np
from scipy.optimize import linear_sum_assignment

RESULTS = pathlib.Path(__file__).resolve().parents[1] / "results"
H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])


@dataclasses.dataclass
class Params:
    dt: float = 1.0                 # s, time between scans
    sigma_accel: float = 1.0        # m/s^2, process noise (white-noise acceleration)
    sigma_meas: float = 10.0        # m, measurement noise per axis
    sigma_prev_pos: float = 20.0    # m, previous estimate uncertainty (position)
    sigma_prev_vel: float = 5.0     # m/s, previous estimate uncertainty (velocity)
    p_detect: float = 0.9
    clutter_per_scan: float = 1.0   # expected false alarms in the window
    window_pad: float = 200.0       # m, clutter window margin around predicted positions
    gate: float | None = 9.21       # chi-square, 2 degrees of freedom, 99%
    spacing: float = 50.0           # m, nominal separation between targets (makes association ambiguous)
    speed: float = 10.0             # m/s


@dataclasses.dataclass
class Scenario:
    z_pred: np.ndarray          # T x 2 predicted measurement positions
    S: np.ndarray               # T x 2 x 2 innovation covariances
    measurements: np.ndarray    # M x 2
    origin: list                # length M: track index that produced it, or -1 for clutter
    clutter_density: float      # false alarms per m^2 (0 when there is no clutter)


def cv_model(dt_s: float, sigma_accel: float) -> tuple[np.ndarray, np.ndarray]:
    F = np.array([[1, 0, dt_s, 0], [0, 1, 0, dt_s], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
    G = np.array([[dt_s ** 2 / 2, 0], [0, dt_s ** 2 / 2], [dt_s, 0], [0, dt_s]])
    return F, sigma_accel ** 2 * G @ G.T


def generate(n_targets: int, params: Params, rng: np.random.Generator) -> Scenario:
    F, Q = cv_model(params.dt, params.sigma_accel)
    R = params.sigma_meas ** 2 * np.eye(2)
    P_prev = np.diag([params.sigma_prev_pos ** 2] * 2 + [params.sigma_prev_vel ** 2] * 2)
    P_pred = F @ P_prev @ F.T + Q
    S_one = H @ P_pred @ H.T + R

    z_pred, S, truths = [], [], []
    for i in range(n_targets):
        heading = rng.uniform(0, 2 * math.pi)
        x_est = np.array([i * params.spacing, rng.normal(0, params.spacing / 2),
                          params.speed * math.cos(heading), params.speed * math.sin(heading)])
        x_true_prev = rng.multivariate_normal(x_est, P_prev)
        x_true = F @ x_true_prev + rng.multivariate_normal(np.zeros(4), Q)
        z_pred.append(H @ F @ x_est)
        S.append(S_one)
        truths.append(H @ x_true)

    measurements, origin = [], []
    for i, position in enumerate(truths):
        if rng.random() < params.p_detect:
            measurements.append(position + rng.multivariate_normal(np.zeros(2), R))
            origin.append(i)

    z_pred = np.array(z_pred)
    clutter_density = 0.0
    if params.clutter_per_scan > 0:
        low = z_pred.min(axis=0) - params.window_pad
        high = z_pred.max(axis=0) + params.window_pad
        clutter_density = params.clutter_per_scan / float(np.prod(high - low))
        for _ in range(rng.poisson(params.clutter_per_scan)):
            measurements.append(rng.uniform(low, high))
            origin.append(-1)

    order = rng.permutation(len(measurements))
    measurements = np.array([measurements[k] for k in order]).reshape(-1, 2)
    origin = [origin[k] for k in order]
    return Scenario(z_pred, np.array(S), measurements, origin, clutter_density)


def mahalanobis2(z: np.ndarray, z_hat: np.ndarray, S: np.ndarray) -> float:
    nu = z - z_hat
    return float(nu @ np.linalg.solve(S, nu))


def pair_cost(z: np.ndarray, z_hat: np.ndarray, S: np.ndarray, p_detect: float, clutter_density: float) -> tuple[float, float]:
    """Return (d^2, cost) with cost = 1/2 d^2 + 1/2 ln|2 pi S| - ln(P_D / lambda)."""
    d2 = mahalanobis2(z, z_hat, S)
    _, logdet = np.linalg.slogdet(2 * math.pi * S)
    return d2, 0.5 * d2 + 0.5 * logdet - math.log(p_detect / clutter_density)


def augmented_cost(scenario: Scenario, params: Params) -> tuple[np.ndarray, dict]:
    if scenario.clutter_density <= 0 or params.p_detect >= 1:
        raise ValueError("augmented matrix needs clutter_density > 0 and p_detect < 1; use pure_cost instead")
    T, M = len(scenario.z_pred), len(scenario.measurements)
    N = T + M
    C = np.full((N, N), np.inf)
    d2 = np.full((T, M), np.inf)
    for i in range(T):
        for j in range(M):
            d2_ij, c_ij = pair_cost(scenario.measurements[j], scenario.z_pred[i], scenario.S[i],
                                    params.p_detect, scenario.clutter_density)
            d2[i, j] = d2_ij
            if params.gate is None or d2_ij <= params.gate:
                C[i, j] = c_ij
    c_miss = -math.log(1 - params.p_detect)
    for i in range(T):
        C[i, M + i] = c_miss
    for j in range(M):
        C[T + j, j] = 0.0
    C[T:, M:] = 0.0
    return C, {"tracks": T, "measurements": M, "c_miss": c_miss, "d2": d2}


def pure_cost(scenario: Scenario) -> np.ndarray:
    """Plain T x T assignment: every target detected, no clutter, no gating."""
    T, M = len(scenario.z_pred), len(scenario.measurements)
    if M != T:
        raise ValueError("pure mode needs exactly one measurement per target")
    C = np.zeros((T, T))
    for i in range(T):
        _, logdet = np.linalg.slogdet(2 * math.pi * scenario.S[i])
        for j in range(T):
            C[i, j] = 0.5 * mahalanobis2(scenario.measurements[j], scenario.z_pred[i], scenario.S[i]) + 0.5 * logdet
    return C


def solve_hungarian(C: np.ndarray, n_tracks: int, n_measurements: int) -> dict:
    rows, cols = linear_sum_assignment(C)
    association = [None] * n_tracks
    for r, c in zip(rows, cols):
        if r < n_tracks and c < n_measurements:
            association[r] = int(c)
    return {"association": association, "total_cost": float(C[rows, cols].sum())}


def truth_association(scenario: Scenario) -> list:
    truth = [None] * len(scenario.z_pred)
    for j, source in enumerate(scenario.origin):
        if source >= 0:
            truth[source] = j
    return truth


def brute_force_min_cost(scenario: Scenario, params: Params) -> float:
    """Independent check: enumerate every valid association directly, without the augmented matrix."""
    T, M = len(scenario.z_pred), len(scenario.measurements)
    _, info = augmented_cost(scenario, params)
    best = math.inf
    for choice in itertools.product([None] + list(range(M)), repeat=T):
        used = [c for c in choice if c is not None]
        if len(used) != len(set(used)):
            continue
        cost = 0.0
        for i, j in enumerate(choice):
            if j is None:
                cost += info["c_miss"]
                continue
            d2, c = pair_cost(scenario.measurements[j], scenario.z_pred[i], scenario.S[i],
                              params.p_detect, scenario.clutter_density)
            if params.gate is not None and d2 > params.gate:
                cost = math.inf
                break
            cost += c
        best = min(best, cost)
    return best


def evaluate(scenario: Scenario, params: Params, pure: bool = False) -> dict:
    T, M = len(scenario.z_pred), len(scenario.measurements)
    C = pure_cost(scenario) if pure else augmented_cost(scenario, params)[0]
    solution = solve_hungarian(C, T, M)
    truth = truth_association(scenario)
    correct = sum(a == t for a, t in zip(solution["association"], truth))
    return {
        "tracks": T,
        "measurements": M,
        "matrix_size": C.shape[0],
        "qubits_if_qubo": C.shape[0] ** 2,
        "association": solution["association"],
        "truth": truth,
        "total_cost": solution["total_cost"],
        "track_accuracy": correct / T,
        "optimum_is_truth": correct == T,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=int, default=3)
    parser.add_argument("--scenes", type=int, default=500)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--pure", action="store_true")
    parser.add_argument("--p-detect", type=float, default=None)
    parser.add_argument("--clutter", type=float, default=None)
    parser.add_argument("--sigma-meas", type=float, default=None)
    parser.add_argument("--spacing", type=float, default=None)
    args = parser.parse_args()

    params = Params()
    if args.pure:
        params = dataclasses.replace(params, p_detect=1.0, clutter_per_scan=0.0, gate=None)
    for name, value in (("p_detect", args.p_detect), ("clutter_per_scan", args.clutter),
                        ("sigma_meas", args.sigma_meas), ("spacing", args.spacing)):
        if value is not None:
            params = dataclasses.replace(params, **{name: value})

    rng = np.random.default_rng(args.seed)
    example = generate(args.targets, params, rng)
    first = evaluate(example, params, pure=args.pure)
    print("example scene: %d tracks, %d measurements (origins %s)" % (first["tracks"], first["measurements"], example.origin))
    print("  Hungarian association : %s" % first["association"])
    print("  truth                 : %s" % first["truth"])
    print("  matrix %dx%d  ->  %d binary variables as a QUBO" % (first["matrix_size"], first["matrix_size"], first["qubits_if_qubo"]))

    rows = [first] + [evaluate(generate(args.targets, params, rng), params, pure=args.pure) for _ in range(args.scenes - 1)]
    sizes = [r["matrix_size"] for r in rows]
    summary = {
        "scenes": args.scenes,
        "mean_track_accuracy": float(np.mean([r["track_accuracy"] for r in rows])),
        "share_optimum_equals_truth": float(np.mean([r["optimum_is_truth"] for r in rows])),
        "matrix_size_min": int(min(sizes)),
        "matrix_size_max": int(max(sizes)),
        "matrix_size_mean": float(np.mean(sizes)),
        "qubits_if_qubo_mean": float(np.mean([r["qubits_if_qubo"] for r in rows])),
    }
    print("baseline over %d scenes:" % args.scenes)
    print("  mean track accuracy (Hungarian vs truth): %.4f" % summary["mean_track_accuracy"])
    print("  scenes where the optimum IS the truth   : %.4f" % summary["share_optimum_equals_truth"])
    print("  matrix size %d..%d (mean %.2f), QUBO variables mean %.1f"
          % (summary["matrix_size_min"], summary["matrix_size_max"], summary["matrix_size_mean"], summary["qubits_if_qubo_mean"]))

    record = {
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P1.0 Hungarian baseline",
        "mode": "pure" if args.pure else "augmented",
        "targets": args.targets,
        "seed": args.seed,
        "params": dataclasses.asdict(params),
        "summary": summary,
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p1_0-baseline-%s-T%d-%s.json" % (record["mode"], args.targets, dt.datetime.now().strftime("%Y%m%d-%H%M%S")))
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
