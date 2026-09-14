# P2.2 - Multi-sensor assignment written as a QUBO, and the gate: QUBO minimum == ILP optimum.
#
# One binary variable x_k per kept tuple k (from p2_scene.build_tuples). Every real measurement m must be covered once:
#
#   E(x) = sum_k c_k x_k + A * sum_m (sum_{k contains m} x_k - 1)^2
#
# Expanded with x^2 = x, as an upper-triangular matrix Q plus a constant:
#   Q[k, k]           = c_k - A * n_k          n_k = number of real measurements in tuple k (1..S)
#   Q[k, l], k < l    = 2A * (number of measurements tuples k and l share)
#   offset            = A * (number of real measurements)
#
# With S = 2 every tuple holds at most two measurements, and this reduces to the P1 form.
#
# Default penalty A = 2 * sum|c| + 1, the same argument as P1.1: any infeasible x pays at least A, its cost part is at least
# -sum|c|, and the optimum costs at most sum|c|. Gated-out tuples have no variable.
#
# Also recorded, not part of the gate: whether the much smaller A = max|c| still leaves the optimum as the minimum.
#
# Usage:
#     python src/p2_qubo.py                     # run the gate on small scenes, save results
#     python src/p2_qubo.py --scenes 200 --max-vars 20

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json

import numpy as np

from p1_qubo import brute_force_minimum, energy
from p2_ilp import measurement_index, solve_ilp
from p2_scene import PURE, RESULTS, Params, build_tuples, generate, is_partition, partition_cost


def members(tup: tuple) -> list:
    return [(s, i) for s, i in enumerate(tup) if i > 0]


def safe_penalty(costs: np.ndarray) -> float:
    return 2.0 * float(np.abs(costs).sum()) + 1.0


def build_qubo(scene, tuple_set, penalty: float | None = None) -> dict:
    index = measurement_index(scene)
    costs = np.asarray(tuple_set.costs, dtype=float)
    A = safe_penalty(costs) if penalty is None else float(penalty)
    K = len(tuple_set.tuples)

    Q = np.zeros((K, K))
    containing: dict = {m: [] for m in index}
    for k, tup in enumerate(tuple_set.tuples):
        ms = members(tup)
        Q[k, k] = costs[k] - A * len(ms)
        for m in ms:
            containing[m].append(k)
    uncovered = [m for m, ks in containing.items() if not ks]
    if uncovered:
        raise ValueError("measurements %s are in no kept tuple - the assignment is infeasible" % uncovered)
    for ks in containing.values():
        for a in range(len(ks)):
            for b in range(a + 1, len(ks)):
                Q[ks[a], ks[b]] += 2.0 * A
    return {"variables": list(tuple_set.tuples), "costs": costs, "Q": Q, "offset": A * len(index), "penalty": A,
            "measurements": len(index)}


def decode(x: np.ndarray, qubo: dict, scene) -> tuple[bool, list]:
    partition = sorted(tup for bit, tup in zip(x, qubo["variables"]) if bit)
    return is_partition(scene, partition), partition


def quadratic_terms(qubo: dict) -> int:
    return int(np.count_nonzero(np.triu(qubo["Q"], 1)))


def check_instance(scene, tuple_set, max_vars: int) -> dict:
    K = len(tuple_set.tuples)
    record = {"variables": K, "measurements": len(measurement_index(scene))}
    ilp = solve_ilp(scene, tuple_set)
    if ilp["status"] not in ("optimal", "empty"):
        # possible without clutter and with P_D = 1: the gate cut a true tuple and no singleton may replace it
        record["status"] = "infeasible"
        return record
    if K > max_vars:
        record["status"] = "skipped"
        return record
    qubo = build_qubo(scene, tuple_set)
    optimum = ilp["cost"]
    e_min, x_min = brute_force_minimum(qubo, max_vars)
    feasible, partition = decode(x_min, qubo, scene)
    decoded_cost = partition_cost(tuple_set, partition) if feasible else None
    tol = 1e-6 * max(1.0, abs(optimum))
    passed = feasible and abs(e_min - optimum) <= tol and abs(decoded_cost - optimum) <= tol

    max_abs = float(np.max(np.abs(tuple_set.costs))) if K else 0.0
    small = build_qubo(scene, tuple_set, penalty=max_abs)
    e_small, x_small = brute_force_minimum(small, max_vars)
    small_feasible, small_partition = decode(x_small, small, scene)
    record.update({
        "status": "pass" if passed else "FAIL",
        "ilp_optimum": optimum,
        "qubo_minimum": e_min,
        "argmin_feasible": feasible,
        "penalty": qubo["penalty"],
        "quadratic_terms": quadratic_terms(qubo),
        "max_abs_cost": max_abs,
        "max_abs_penalty_minimum_is_optimum": bool(small_feasible and abs(e_small - optimum) <= tol),
        "max_abs_penalty_argmin_feasible": bool(small_feasible),
    })
    return record


SETTINGS = (
    ("default", 1, {}),
    ("default", 2, {}),
    ("bearing 0.005 rad", 2, {"sigma_bearing": 0.005}),
    ("bearing 0.005 rad", 3, {"sigma_bearing": 0.005}),
    ("pure", 2, dict(PURE)),
    ("P_D 1, no clutter, gated", 3, {"p_detect": 1.0, "clutter_per_sensor": 0.0}),
    ("P_D 1, no clutter, gated, bearing 0.005 rad", 3, {"p_detect": 1.0, "clutter_per_sensor": 0.0, "sigma_bearing": 0.005}),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2029)
    parser.add_argument("--max-vars", type=int, default=20)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    base = Params()
    summary, records = [], []
    print("setting                                      T  tested  passed  skipped  infeasible  vars mean/max  quad terms mean  A=max|c| exact")
    for name, T, change in SETTINGS:
        params = dataclasses.replace(base, **change)
        rows = []
        for _ in range(args.scenes):
            scene = generate(T, params, rng)
            rec = check_instance(scene, build_tuples(scene, params), args.max_vars)
            rec.update({"setting": name, "targets": T})
            rows.append(rec)
        records += rows
        tested = [r for r in rows if r["status"] in ("pass", "FAIL")]
        row = {
            "setting": name, "targets": T, "change": change,
            "tested": len(tested),
            "passed": sum(r["status"] == "pass" for r in tested),
            "skipped": sum(r["status"] == "skipped" for r in rows),
            "infeasible": sum(r["status"] == "infeasible" for r in rows),
            "variables_mean": float(np.mean([r["variables"] for r in rows])),
            "variables_max": int(max(r["variables"] for r in rows)),
            "tested_variables_mean": float(np.mean([r["variables"] for r in tested])) if tested else None,
            "quadratic_terms_mean": float(np.mean([r["quadratic_terms"] for r in tested])) if tested else None,
            "max_abs_penalty_exact": sum(r["max_abs_penalty_minimum_is_optimum"] for r in tested),
        }
        summary.append(row)
        print("%-44s %d  %6d  %6d  %7d  %10d  %6.1f / %3d  %15s  %d / %d"
              % (name, T, row["tested"], row["passed"], row["skipped"], row["infeasible"], row["variables_mean"],
                 row["variables_max"],
                 "%.1f" % row["quadratic_terms_mean"] if tested else "-", row["max_abs_penalty_exact"], row["tested"]))

    total_tested = sum(r["tested"] for r in summary)
    total_passed = sum(r["passed"] for r in summary)
    gate_open = total_tested > 0 and total_passed == total_tested
    print("GATE %s: %d / %d instances where the QUBO minimum equals the ILP optimum"
          % ("PASSED" if gate_open else "FAILED", total_passed, total_tested))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p2_2-qubo-gate-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps({
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P2.2 QUBO gate",
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
