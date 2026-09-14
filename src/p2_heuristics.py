# P2.3 - Classical baselines scored against the exact optimum: greedy, Lagrangian relaxation, simulated annealing - and H2.
#
# Greedy: take tuples cheapest first, skipping any tuple that reuses a measurement.
#
# Lagrangian relaxation (three sensors): relax "each measurement of sensor 3 is used once" with multipliers u_j.
#   L(u) = sum_j u_j + min over x of sum_k (c_k - u_{i3(k)}) x_k, subject only to the sensor-1 and sensor-2 constraints.
#   The inner problem is a two-dimensional assignment with dummies: each (i1, i2) keeps its best i3, and tuples (0, 0, i3)
#   are unconstrained, so they are taken whenever their reduced cost is negative. L(u) is a lower bound on the optimum.
#   Multipliers follow subgradient steps (Polyak step towards the best upper bound; theta starts at 2 and halves after
#   10 iterations without a better bound; at most 200 iterations; stop when the bounds meet).
#   Every iteration also recovers a feasible answer - an upper bound. It keeps the relaxed (i1, i2) pairs and assigns the
#   sensor-3 measurements to them with a second 2D assignment.
#   The inner problem has integral solutions (each tuple sits in at most one sensor-1 and one sensor-2 constraint), so the best
#   possible Lagrangian bound equals the LP relaxation of the ILP. The "duality gap" below is therefore ILP optimum - LP bound,
#   computed exactly with HiGHS. How far the subgradient's own bound falls short of it is reported separately.
#
# Simulated annealing: p1_penalty.anneal (P1 schedule, 64 restarts, 100 sweeps) on the P2.2 QUBO with A = max(max|c|, 1) -
# P2.2 found that max|c| needs a positive floor.
#
# H2 as registered: "Lagrangian relaxation reaches the exact optimum on most low-clutter instances, and the share of instances
# with a nonzero duality gap rises with clutter density and with target density (closer spacing)".
# Made operational here, written before the first run:
#   - "most": the LR upper bound equals the ILP optimum in more than half the scenes at clutter 0 and at clutter 0.5
#   - "rises": the share of scenes with a gap is higher at clutter 2 than at clutter 0, and higher at spacing 25 m than at 100 m,
#     each with non-overlapping 95% Wilson intervals. The right direction with overlapping intervals counts as partly held.
#   - "nonzero gap": ILP optimum - LP bound > 1e-6 * max(1, |optimum|)
#   - scenes: T = 4, 200 per setting; other parameters at their defaults
#   - overall: held if all three parts hold, failed if all three fail, partly held otherwise
#
# Usage:
#     python src/p2_heuristics.py
#     python src/p2_heuristics.py --scenes 400 --sa-scenes 80

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import time

import numpy as np
from scipy.optimize import linear_sum_assignment

from p1_penalty import anneal
from p2_ilp import lp_relaxation, solve_ilp, wilson
from p2_qubo import build_qubo, decode, members
from p2_scene import RESULTS, Params, build_tuples, generate, is_partition, partition_cost

TOL = 1e-6


def tol(value: float) -> float:
    return TOL * max(1.0, abs(value))


def greedy(scene, tuple_set) -> dict:
    used, chosen = set(), []
    for k in np.argsort(tuple_set.costs, kind="stable"):
        ms = members(tuple_set.tuples[k])
        if any(m in used for m in ms):
            continue
        used.update(ms)
        chosen.append(tuple_set.tuples[k])
    partition = sorted(chosen)
    feasible = is_partition(scene, partition)
    return {"feasible": feasible, "partition": partition,
            "cost": partition_cost(tuple_set, partition) if feasible else math.inf}


def lr_structure(tuple_set) -> tuple[dict, dict]:
    lookup = {tup: float(c) for tup, c in zip(tuple_set.tuples, tuple_set.costs)}
    pairs: dict = {}
    for tup, c in lookup.items():
        pairs.setdefault(tup[:2], []).append((tup[2], c))
    return lookup, pairs


def lagrangian_value(scene, tuple_set, u: np.ndarray, structure=None) -> tuple[float, list | None]:
    """L(u) and the tuples of the relaxed solution. u[j] is the multiplier of sensor-3 measurement j; u[0] is ignored."""
    _, pairs = structure or lr_structure(tuple_set)
    M1, M2 = len(scene.measurements[0]), len(scene.measurements[1])
    total = float(np.sum(u[1:]))
    chosen, best_cell = [], {}
    for pair, options in pairs.items():
        reduced = [(c - (u[i3] if i3 > 0 else 0.0), i3) for i3, c in options]
        if pair == (0, 0):
            for value, i3 in reduced:
                if value < 0:
                    total += value
                    chosen.append((0, 0, i3))
        else:
            best_cell[pair] = min(reduced)
    N = M1 + M2
    if N:
        C = np.full((N, N), np.inf)
        for (i1, i2), (value, _) in best_cell.items():
            if i1 and i2:
                C[i1 - 1, i2 - 1] = value
            elif i1:
                C[i1 - 1, M2 + i1 - 1] = value
            else:
                C[M1 + i2 - 1, i2 - 1] = value
        C[M1:, M2:] = 0.0
        try:
            rows, cols = linear_sum_assignment(C)
        except ValueError:
            return math.inf, None
        total += float(C[rows, cols].sum())
        for a, b in zip(rows, cols):
            if a < M1 and b < M2:
                pair = (a + 1, b + 1)
            elif a < M1:
                pair = (a + 1, 0)
            elif b < M2:
                pair = (0, b + 1)
            else:
                continue
            chosen.append(pair + (best_cell[pair][1],))
    return total, chosen


def recover(scene, tuple_set, chosen: list, lookup: dict) -> tuple[float, list | None]:
    """Keep the relaxed (i1, i2) pairs; assign sensor-3 measurements to them optimally."""
    M3 = len(scene.measurements[2])
    pairs = sorted({t[:2] for t in chosen if t[:2] != (0, 0)})
    P = len(pairs)
    N = P + M3
    if N == 0:
        return 0.0, []
    C = np.full((N, N), np.inf)
    for p, pair in enumerate(pairs):
        for j in range(1, M3 + 1):
            C[p, j - 1] = lookup.get(pair + (j,), np.inf)
        C[p, M3 + p] = lookup.get(pair + (0,), np.inf)
    for j in range(1, M3 + 1):
        C[P + j - 1, j - 1] = lookup.get((0, 0, j), np.inf)
    C[P:, M3:] = 0.0
    try:
        rows, cols = linear_sum_assignment(C)
    except ValueError:
        return math.inf, None
    partition = []
    for a, b in zip(rows, cols):
        if a < P:
            partition.append(pairs[a] + ((b + 1) if b < M3 else 0,))
        elif b < M3:
            partition.append((0, 0, b + 1))
    partition = sorted(partition)
    return partition_cost(tuple_set, partition), partition


def lagrangian_relaxation(scene, tuple_set, iterations: int = 200) -> dict:
    if len(scene.sensors) != 3:
        raise ValueError("this relaxation is written for three sensors")
    structure = lr_structure(tuple_set)
    lookup = structure[0]
    M3 = len(scene.measurements[2])
    u = np.zeros(M3 + 1)
    best_lb, best_ub, best_partition = -math.inf, math.inf, None
    theta, stall, used = 2.0, 0, 0
    for it in range(iterations):
        used = it + 1
        value, chosen = lagrangian_value(scene, tuple_set, u, structure)
        if chosen is None:
            return {"status": "infeasible", "lower_bound": math.inf, "upper_bound": math.inf, "partition": None,
                    "iterations": used, "certified": False}
        if value > best_lb + 1e-12:
            best_lb, stall = value, 0
        else:
            stall += 1
            if stall >= 10:
                theta, stall = theta / 2, 0
        ub, partition = recover(scene, tuple_set, chosen, lookup)
        if ub < best_ub:
            best_ub, best_partition = ub, partition
        if best_ub - best_lb <= tol(best_ub):
            break
        g = np.ones(M3)
        for t in chosen:
            if t[2] > 0:
                g[t[2] - 1] -= 1
        norm = float(g @ g)
        if norm == 0:
            break
        target = best_ub if math.isfinite(best_ub) else value + abs(value) + 1.0
        u[1:] += theta * max(target - value, 1e-9) / norm * g
    return {"status": "ok", "lower_bound": best_lb, "upper_bound": best_ub, "partition": best_partition,
            "iterations": used, "certified": best_ub - best_lb <= tol(best_ub)}


def anneal_study(scene, tuple_set, optimum: float, restarts: int, sweeps: int, rng) -> dict:
    penalty = max(float(np.max(np.abs(tuple_set.costs))), 1.0)
    qubo = build_qubo(scene, tuple_set, penalty=penalty)
    feasible = optimal = 0
    for x in anneal(qubo, restarts, sweeps, rng):
        ok, partition = decode(x, qubo, scene)
        if ok:
            feasible += 1
            optimal += abs(partition_cost(tuple_set, partition) - optimum) <= tol(optimum)
    return {"penalty": penalty, "feasible_share": feasible / restarts, "success": optimal / restarts,
            "best_of_restarts_optimal": optimal > 0}


H2_SETTINGS = (
    ("clutter 0", {"clutter_per_sensor": 0.0}),
    ("clutter 0.5", {"clutter_per_sensor": 0.5}),
    ("clutter 1 (default)", {}),
    ("clutter 2", {"clutter_per_sensor": 2.0}),
    ("spacing 25 m", {"spacing": 25.0}),
    ("spacing 100 m", {"spacing": 100.0}),
)


def run_setting(name: str, change: dict, T: int, scenes: int, sa_scenes: int, restarts: int, sweeps: int,
                rng, sa_rng) -> dict:
    params = dataclasses.replace(Params(), **change)
    rows, infeasible = [], 0
    violations = {"lp_above_optimum": 0, "lr_lower_above_lp": 0, "lr_upper_below_optimum": 0,
                  "lr_partition_invalid": 0, "greedy_below_optimum": 0}
    start = time.perf_counter()
    for n in range(scenes):
        scene = generate(T, params, rng)
        ts = build_tuples(scene, params)
        ilp = solve_ilp(scene, ts)
        if ilp["status"] not in ("optimal", "empty"):
            infeasible += 1
            continue
        optimum = ilp["cost"]
        lp = lp_relaxation(scene, ts)
        lr = lagrangian_relaxation(scene, ts)
        gr = greedy(scene, ts)
        gap = optimum - lp["bound"]
        row = {
            "scene": n, "tuples": len(ts.tuples), "optimum": optimum, "lp_bound": lp["bound"],
            "lp_fractional_variables": lp["fractional_variables"],
            "duality_gap": gap, "has_gap": gap > tol(optimum),
            "lr_lower": lr["lower_bound"], "lr_upper": lr["upper_bound"], "lr_iterations": lr["iterations"],
            "lr_certified": lr["certified"], "lr_reaches_optimum": abs(lr["upper_bound"] - optimum) <= tol(optimum),
            "lr_bound_short_of_lp": lp["bound"] - lr["lower_bound"],
            "greedy_feasible": gr["feasible"],
            "greedy_optimal": gr["feasible"] and abs(gr["cost"] - optimum) <= tol(optimum),
            "greedy_excess": gr["cost"] - optimum if gr["feasible"] else None,
        }
        violations["lp_above_optimum"] += lp["bound"] > optimum + tol(optimum)
        violations["lr_lower_above_lp"] += lr["lower_bound"] > lp["bound"] + tol(optimum)
        violations["lr_upper_below_optimum"] += lr["upper_bound"] < optimum - tol(optimum)
        violations["lr_partition_invalid"] += lr["partition"] is None or not is_partition(scene, lr["partition"])
        violations["greedy_below_optimum"] += gr["feasible"] and gr["cost"] < optimum - tol(optimum)
        if n < sa_scenes:
            row["sa"] = anneal_study(scene, ts, optimum, restarts, sweeps, sa_rng)
        rows.append(row)

    k = len(rows)
    gaps = sum(r["has_gap"] for r in rows)
    reach = sum(r["lr_reaches_optimum"] for r in rows)
    sa_rows = [r["sa"] for r in rows if "sa" in r]
    greedy_excess = [r["greedy_excess"] for r in rows if r["greedy_excess"] is not None and not r["greedy_optimal"]]
    return {
        "setting": name, "targets": T, "change": change, "scenes": scenes, "infeasible": infeasible, "solved": k,
        "tuples_mean": float(np.mean([r["tuples"] for r in rows])),
        "share_with_gap": gaps / k, "share_with_gap_wilson95": wilson(gaps, k),
        "lr_reaches_optimum": reach / k, "lr_reaches_optimum_wilson95": wilson(reach, k),
        "lr_certified": sum(r["lr_certified"] for r in rows) / k,
        "lr_iterations_median": float(np.median([r["lr_iterations"] for r in rows])),
        "lr_bound_short_of_lp_median": float(np.median([r["lr_bound_short_of_lp"] for r in rows])),
        "lr_bound_short_of_lp_max": float(max(r["lr_bound_short_of_lp"] for r in rows)),
        "lr_reaches_optimum_when_no_gap": (sum(r["lr_reaches_optimum"] for r in rows if not r["has_gap"])
                                           / max(1, k - gaps)),
        "lr_reaches_optimum_when_gap": sum(r["lr_reaches_optimum"] for r in rows if r["has_gap"]) / max(1, gaps),
        "greedy_feasible": sum(r["greedy_feasible"] for r in rows) / k,
        "greedy_optimal": sum(r["greedy_optimal"] for r in rows) / k,
        "greedy_excess_median_when_not_optimal": float(np.median(greedy_excess)) if greedy_excess else None,
        "sa_scenes": len(sa_rows),
        "sa_best_of_restarts_optimal": sum(s["best_of_restarts_optimal"] for s in sa_rows) / max(1, len(sa_rows)),
        "sa_success_mean": float(np.mean([s["success"] for s in sa_rows])) if sa_rows else None,
        "sa_feasible_share_mean": float(np.mean([s["feasible_share"] for s in sa_rows])) if sa_rows else None,
        "violations": violations,
        "hard_subset_scene_indices": [r["scene"] for r in rows if r["has_gap"]],
        "seconds": time.perf_counter() - start,
        "instances": rows,
    }


def compare(high: dict, low: dict) -> str:
    """'held' if high's gap share is above low's with non-overlapping 95% intervals, 'partly held' if only above."""
    if high["share_with_gap_wilson95"][0] > low["share_with_gap_wilson95"][1]:
        return "held"
    return "partly held" if high["share_with_gap"] > low["share_with_gap"] else "failed"


def verdict(results: dict) -> dict:
    most = all(results[name]["lr_reaches_optimum"] > 0.5 for name in ("clutter 0", "clutter 0.5"))
    clutter = compare(results["clutter 2"], results["clutter 0"])
    spacing = compare(results["spacing 25 m"], results["spacing 100 m"])
    parts = ["held" if most else "failed", clutter, spacing]
    if all(p == "held" for p in parts):
        overall = "held"
    elif all(p == "failed" for p in parts):
        overall = "failed"
    else:
        overall = "partly held"
    return {"lr_reaches_optimum_on_most_low_clutter": most, "gap_rises_with_clutter": clutter,
            "gap_rises_with_closer_spacing": spacing, "H2": overall}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=int, default=200)
    parser.add_argument("--sa-scenes", type=int, default=40)
    parser.add_argument("--restarts", type=int, default=64)
    parser.add_argument("--sweeps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2030)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    sa_rng = np.random.default_rng(args.seed + 1)
    results = {}
    header = ("setting                T  solved  gap share [95%]        LR = opt [95%]         LR cert  LR short of LP"
              "  greedy opt  SA best-of-64 opt  SA success  SA feasible  s")
    print(header)

    def show(r):
        print("%-21s  %d  %6d  %.3f [%.3f, %.3f]  %.3f [%.3f, %.3f]  %7.3f  %14.2e  %10.3f  %17.3f  %10.3f  %11.3f  %4.0f"
              % (r["setting"], r["targets"], r["solved"], r["share_with_gap"], *r["share_with_gap_wilson95"],
                 r["lr_reaches_optimum"], *r["lr_reaches_optimum_wilson95"], r["lr_certified"],
                 r["lr_bound_short_of_lp_median"], r["greedy_optimal"], r["sa_best_of_restarts_optimal"],
                 r["sa_success_mean"] or 0.0, r["sa_feasible_share_mean"] or 0.0, r["seconds"]))
        if any(r["violations"].values()) or r["infeasible"]:
            print("      special cases: infeasible %d, %s" % (r["infeasible"], r["violations"]))

    for name, change in H2_SETTINGS:
        results[name] = run_setting(name, change, 4, args.scenes, args.sa_scenes, args.restarts, args.sweeps, rng, sa_rng)
        show(results[name])
    decision = verdict(results)
    print("H2: %s" % decision)

    print("size, default parameters (not part of the H2 verdict):")
    sizes = {}
    for T in (2, 6):
        sizes[str(T)] = run_setting("default T=%d" % T, {}, T, args.scenes // 2, args.sa_scenes // 2,
                                    args.restarts, args.sweeps, rng, sa_rng)
        show(sizes[str(T)])

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p2_3-heuristics-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps({
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P2.3 classical baselines and H2",
        "seed": args.seed,
        "annealing": {"restarts": args.restarts, "sweeps": args.sweeps, "penalty": "max(max|c|, 1)"},
        "lagrangian": {"iterations_max": 200, "theta_start": 2.0, "halve_after": 10},
        "h2_verdict": decision,
        "h2_settings": results,
        "sizes": sizes,
    }, indent=2, default=to_builtin), encoding="utf-8")
    print("saved " + str(out))


def to_builtin(value):
    """numpy scalars (from counting numpy booleans) are not JSON-serialisable; write them as plain numbers."""
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError("cannot serialise %r" % type(value))


if __name__ == "__main__":
    main()
