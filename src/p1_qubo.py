# P1.1 - Assignment written as a QUBO, and the hard gate: QUBO minimum == Hungarian optimum.
#
# One binary variable x_ij per allowed (finite-cost) cell of an n x n assignment matrix C:
#
#   E(x) = sum_ij c_ij x_ij + A * sum_i (sum_j x_ij - 1)^2 + A * sum_j (sum_i x_ij - 1)^2
#
# Expanded with x^2 = x, as an upper-triangular matrix Q plus a constant:
#   Q[k, k]           = c_k - 2A                      (every variable is in one row and one column)
#   Q[k, l], k < l    = 2A for each pair sharing a row, and 2A for each pair sharing a column
#   offset            = 2nA
#
# Gated-out cells (infinite cost) get no variable at all: fewer qubits, no big-M numbers.
#
# Default penalty A = 2 * sum|c| + 1. Any infeasible x violates at least one constraint, so its penalty is
# at least A, and its cost part is at least -sum|c|; the best feasible cost is at most sum|c|. Hence every
# infeasible x has higher energy than the optimum. P1.2 studies how much smaller A can safely be.
#
# Pruning the augmented matrix: the dummy x dummy block (clutter row T+j, miss column M+i) only needs a
# cell where track i is allowed to take measurement j - exactly the pairs that complete a real assignment.
# Every valid association still has a completion with the same cost, with far fewer variables.
#
# Usage:
#     python src/p1_qubo.py                     # run the gate on random scenes, save results
#     python src/p1_qubo.py --scenes 200 --max-vars 20

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json

import numpy as np
from scipy.optimize import linear_sum_assignment

from p1_scenario import RESULTS, Params, augmented_cost, generate, pure_cost


def prune_augmented(C: np.ndarray, n_tracks: int, n_measurements: int) -> np.ndarray:
    T, M = n_tracks, n_measurements
    P = C.copy()
    P[T:, M:] = np.inf
    for i in range(T):
        for j in range(M):
            if np.isfinite(C[i, j]):
                P[T + j, M + i] = 0.0
    return P


def safe_penalty(costs: np.ndarray) -> float:
    return 2.0 * float(np.abs(costs).sum()) + 1.0


def build_qubo(C: np.ndarray, penalty: float | None = None) -> dict:
    n = C.shape[0]
    variables = [(i, j) for i in range(n) for j in range(n) if np.isfinite(C[i, j])]
    costs = np.array([C[i, j] for i, j in variables])
    A = safe_penalty(costs) if penalty is None else float(penalty)
    m = len(variables)

    Q = np.zeros((m, m))
    by_row: dict[int, list[int]] = {}
    by_col: dict[int, list[int]] = {}
    for k, (i, j) in enumerate(variables):
        Q[k, k] = costs[k] - 2.0 * A
        by_row.setdefault(i, []).append(k)
        by_col.setdefault(j, []).append(k)
    if len(by_row) != n or len(by_col) != n:
        raise ValueError("some row or column has no allowed cell - the assignment is infeasible")
    for group in list(by_row.values()) + list(by_col.values()):
        for a in range(len(group)):
            for b in range(a + 1, len(group)):
                Q[group[a], group[b]] += 2.0 * A
    return {"n": n, "variables": variables, "costs": costs, "Q": Q, "offset": 2.0 * n * A, "penalty": A}


def energy(qubo: dict, x: np.ndarray) -> np.ndarray:
    X = np.atleast_2d(x).astype(float)
    return np.einsum("bi,ij,bj->b", X, qubo["Q"], X) + qubo["offset"]


def brute_force_minimum(qubo: dict, max_vars: int = 22, chunk: int = 1 << 16) -> tuple[float, np.ndarray]:
    m = len(qubo["variables"])
    if m > max_vars:
        raise ValueError("%d variables is above the brute-force limit of %d" % (m, max_vars))
    best_energy, best_x = np.inf, None
    shifts = np.arange(m, dtype=np.int64)
    for start in range(0, 1 << m, chunk):
        idx = np.arange(start, min(start + chunk, 1 << m), dtype=np.int64)
        X = ((idx[:, None] >> shifts) & 1).astype(float)
        E = np.einsum("bi,ij,bj->b", X, qubo["Q"], X) + qubo["offset"]
        k = int(np.argmin(E))
        if E[k] < best_energy:
            best_energy, best_x = float(E[k]), X[k].astype(int)
    return best_energy, best_x


def row_col_sums(x: np.ndarray, variables: list, n: int) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = np.zeros(n, dtype=int), np.zeros(n, dtype=int)
    for bit, (i, j) in zip(x, variables):
        if bit:
            rows[i] += 1
            cols[j] += 1
    return rows, cols


def decode(x: np.ndarray, qubo: dict) -> tuple[bool, list]:
    n = qubo["n"]
    rows, cols = row_col_sums(x, qubo["variables"], n)
    permutation = [None] * n
    for bit, (i, j) in zip(x, qubo["variables"]):
        if bit:
            permutation[i] = j
    return bool(np.all(rows == 1) and np.all(cols == 1)), permutation


def hungarian_cost(C: np.ndarray) -> float:
    r, c = linear_sum_assignment(C)
    return float(C[r, c].sum())


def check_instance(C: np.ndarray, max_vars: int) -> dict:
    qubo = build_qubo(C)
    m = len(qubo["variables"])
    record = {"n": qubo["n"], "variables": m, "penalty": qubo["penalty"]}
    if m > max_vars:
        record["status"] = "skipped"
        return record
    optimum = hungarian_cost(C)
    e_min, x_min = brute_force_minimum(qubo, max_vars)
    feasible, permutation = decode(x_min, qubo)
    decoded_cost = float(sum(C[i, j] for i, j in enumerate(permutation))) if feasible else None
    tol = 1e-6 * max(1.0, abs(optimum))
    passed = feasible and abs(e_min - optimum) <= tol and abs(decoded_cost - optimum) <= tol
    record.update({"status": "pass" if passed else "FAIL", "hungarian": optimum, "qubo_minimum": e_min,
                   "argmin_feasible": feasible})
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--max-vars", type=int, default=20)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    base = Params()
    pure_params = dataclasses.replace(base, p_detect=1.0, clutter_per_scan=0.0, gate=None)
    settings = [("pure", 2), ("pure", 3), ("pure", 4), ("augmented", 1), ("augmented", 2), ("augmented", 3)]

    summary, records = [], []
    print("setting        tested  passed  skipped  vars(mean, max)   full-vs-pruned vars")
    for mode, n_targets in settings:
        tested = passed = skipped = 0
        var_counts, full_counts = [], []
        for _ in range(args.scenes):
            if mode == "pure":
                C = pure_cost(generate(n_targets, pure_params, rng))
                full = C.size
            else:
                scene = generate(n_targets, base, rng)
                C_full, info = augmented_cost(scene, base)
                full = int(np.isfinite(C_full).sum())
                C = prune_augmented(C_full, info["tracks"], info["measurements"])
                if abs(hungarian_cost(C) - hungarian_cost(C_full)) > 1e-9:
                    raise SystemExit("pruning changed the optimum - stop")
            rec = check_instance(C, args.max_vars)
            rec.update({"mode": mode, "targets": n_targets, "full_augmented_variables": full})
            records.append(rec)
            full_counts.append(full)
            var_counts.append(rec["variables"])
            if rec["status"] == "skipped":
                skipped += 1
            else:
                tested += 1
                passed += rec["status"] == "pass"
        row = {"mode": mode, "targets": n_targets, "tested": tested, "passed": passed, "skipped": skipped,
               "variables_mean": float(np.mean(var_counts)), "variables_max": int(max(var_counts)),
               "full_variables_mean": float(np.mean(full_counts))}
        summary.append(row)
        print("%-9s T=%d  %6d  %6d  %7d   %5.1f, %3d        %5.1f -> %5.1f"
              % (mode, n_targets, tested, passed, skipped, row["variables_mean"], row["variables_max"],
                 row["full_variables_mean"], row["variables_mean"]))

    total_tested = sum(r["tested"] for r in summary)
    total_passed = sum(r["passed"] for r in summary)
    gate_open = total_tested > 0 and total_passed == total_tested
    print("GATE %s: %d / %d instances where the QUBO minimum equals the Hungarian optimum"
          % ("PASSED" if gate_open else "FAILED", total_passed, total_tested))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p1_1-gate-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    out.write_text(json.dumps({
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P1.1 QUBO gate",
        "seed": args.seed,
        "scenes_per_setting": args.scenes,
        "max_brute_force_variables": args.max_vars,
        "penalty_rule": "A = 2 * sum|c| + 1",
        "gate_passed": gate_open,
        "summary": summary,
        "instances": records,
    }, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
