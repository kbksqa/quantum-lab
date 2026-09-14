# P1.3 - Simulated annealing baseline.
#
# Three parts, all saving per-instance results:
#
# 1. The P1.2 anomaly. P1.2 used A = s * base with base = A_crit, but fell back to base = 1e-6 when A_crit = 0.
#    For those instances every multiplier row had essentially no penalty. This part rebuilds exactly the P1.2
#    instance sets (same seed, same generation order), counts A_crit = 0 instances, and compares annealing
#    under the P1.2 rule (50 * base) and the safe penalty for the two groups.
#
# 2. A computable penalty rule. A_crit needs enumeration, so a real solver cannot use it. On the same instances,
#    compare A = max|c| (computable) with the oracle 1.5 * A_crit and the safe penalty.
#
# 3. Beyond brute force. Pure 5x5 and 6x6 and augmented 3-target scenes with A = max|c| and two annealing
#    budgets, scored against the Hungarian optimum (always computable).
#
# Annealing: p1_penalty.anneal (single-bit flips, geometric schedule from the largest single-flip |dE| down to
# 0.05 * cost spread). Results depend on that schedule.
#
# Usage:
#     python src/p1_annealing.py
#     python src/p1_annealing.py --restarts 64 --scaling-instances 30

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json

import numpy as np

from p1_penalty import anneal, critical_penalty, enumerate_strings
from p1_qubo import build_qubo, hungarian_cost, prune_augmented, safe_penalty
from p1_scenario import RESULTS, Params, augmented_cost, generate, pure_cost


def p1_2_instances(seed: int = 12, instances: int = 50, max_vars: int = 18) -> dict:
    """Rebuild exactly the instance sets of P1.2: same seed, same order of random draws."""
    rng = np.random.default_rng(seed)
    base = Params()
    pure = dataclasses.replace(base, p_detect=1.0, clutter_per_scan=0.0, gate=None)
    sets = {"pure 3x3": [], "pure 4x4": [], "augmented 2 targets": []}
    while min(len(v) for v in sets.values()) < instances:
        if len(sets["pure 3x3"]) < instances:
            sets["pure 3x3"].append(pure_cost(generate(3, pure, rng)))
        if len(sets["pure 4x4"]) < instances:
            sets["pure 4x4"].append(pure_cost(generate(4, pure, rng)))
        if len(sets["augmented 2 targets"]) < instances:
            scene = generate(2, base, rng)
            C, info = augmented_cost(scene, base)
            P = prune_augmented(C, info["tracks"], info["measurements"])
            if int(np.isfinite(P).sum()) <= max_vars:
                sets["augmented 2 targets"].append(P)
    return sets


def max_abs_rule(C: np.ndarray) -> float:
    return float(np.abs(C[np.isfinite(C)]).max())


def score(states: np.ndarray, qubo: dict, optimum: float) -> dict:
    n = qubo["n"]
    rows = np.zeros((states.shape[0], n), dtype=int)
    cols = np.zeros((states.shape[0], n), dtype=int)
    for k, (i, j) in enumerate(qubo["variables"]):
        rows[:, i] += states[:, k]
        cols[:, j] += states[:, k]
    feasible = np.all(rows == 1, axis=1) & np.all(cols == 1, axis=1)
    cost = states @ qubo["costs"]
    optimal = feasible & (np.abs(cost - optimum) <= 1e-6 * max(1.0, abs(optimum)))
    spread = float(qubo["costs"].max() - qubo["costs"].min()) or 1.0
    best_feasible = float(cost[feasible].min()) if feasible.any() else None
    return {
        "success": float(optimal.mean()),
        "best_of_restarts_optimal": bool(optimal.any()),
        "feasible_share": float(feasible.mean()),
        "best_gap_over_spread": None if best_feasible is None else (best_feasible - optimum) / spread,
    }


def part1_anomaly(sets: dict, restarts: int, sweeps: int, rng: np.random.Generator) -> dict:
    rows = []
    for index, C in enumerate(sets["augmented 2 targets"]):
        optimum = hungarian_cost(C)
        strings = enumerate_strings(C)
        a_crit = critical_penalty(strings, optimum)
        base = a_crit if a_crit > 0 else 1e-6
        a_safe = safe_penalty(strings["costs"])
        record = {"index": index, "variables": len(strings["variables"]), "A_crit": a_crit}
        for label, A in (("p1_2_rule_x50", 50 * base), ("safe", a_safe)):
            qubo = build_qubo(C, penalty=A)
            record[label] = score(anneal(qubo, restarts, sweeps, rng), qubo, optimum)
        rows.append(record)

    def group(filter_fn):
        chosen = [r for r in rows if filter_fn(r)]
        if not chosen:
            return {"instances": 0}
        return {
            "instances": len(chosen),
            "feasible_share_p1_2_rule_x50": float(np.mean([r["p1_2_rule_x50"]["feasible_share"] for r in chosen])),
            "feasible_share_safe": float(np.mean([r["safe"]["feasible_share"] for r in chosen])),
        }

    return {
        "zero_A_crit": group(lambda r: r["A_crit"] == 0),
        "positive_A_crit": group(lambda r: r["A_crit"] > 0),
        "all": group(lambda r: True),
        "instances": rows,
    }


def part2_rules(sets: dict, restarts: int, sweeps: int, rng: np.random.Generator) -> dict:
    out = {}
    for name, matrices in sets.items():
        rows = []
        for index, C in enumerate(matrices):
            optimum = hungarian_cost(C)
            strings = enumerate_strings(C)
            a_crit = critical_penalty(strings, optimum)
            a_max = max_abs_rule(C)
            record = {"index": index, "A_crit": a_crit, "A_max_abs": a_max,
                      "max_abs_over_crit": (a_max / a_crit) if a_crit > 0 else None}
            penalties = [("max_abs", a_max), ("safe", safe_penalty(strings["costs"]))]
            if a_crit > 0:
                penalties.insert(0, ("oracle_1.5x_crit", 1.5 * a_crit))
            for label, A in penalties:
                qubo = build_qubo(C, penalty=A)
                record[label] = score(anneal(qubo, restarts, sweeps, rng), qubo, optimum)
            rows.append(record)

        def mean_of(label, key):
            values = [r[label][key] for r in rows if label in r]
            return float(np.mean(values)) if values else None

        ratios = [r["max_abs_over_crit"] for r in rows if r["max_abs_over_crit"] is not None]
        out[name] = {
            "instances": len(rows),
            "zero_A_crit_instances": sum(r["A_crit"] == 0 for r in rows),
            "max_abs_over_crit_median": float(np.median(ratios)) if ratios else None,
            "max_abs_over_crit_min": float(np.min(ratios)) if ratios else None,
            "max_abs_over_crit_max": float(np.max(ratios)) if ratios else None,
            "by_rule": {label: {"success": mean_of(label, "success"),
                                "best_of_restarts_optimal": mean_of(label, "best_of_restarts_optimal"),
                                "feasible_share": mean_of(label, "feasible_share")}
                        for label in ("oracle_1.5x_crit", "max_abs", "safe")},
            "instances_detail": rows,
        }
    return out


def part3_scaling(instances: int, restarts: int, budgets: list, rng: np.random.Generator) -> dict:
    base = Params()
    pure = dataclasses.replace(base, p_detect=1.0, clutter_per_scan=0.0, gate=None)
    builders = {
        "pure 5x5": lambda: pure_cost(generate(5, pure, rng)),
        "pure 6x6": lambda: pure_cost(generate(6, pure, rng)),
        "augmented 3 targets": lambda: (lambda scene: (lambda C, info: prune_augmented(
            C, info["tracks"], info["measurements"]))(*augmented_cost(scene, base)))(generate(3, base, rng)),
    }
    out = {}
    for name, build in builders.items():
        matrices = [build() for _ in range(instances)]
        rows = []
        for index, C in enumerate(matrices):
            optimum = hungarian_cost(C)
            qubo = build_qubo(C, penalty=max_abs_rule(C))
            record = {"index": index, "variables": len(qubo["variables"])}
            for sweeps in budgets:
                record["sweeps_%d" % sweeps] = score(anneal(qubo, restarts, sweeps, rng), qubo, optimum)
            rows.append(record)
        summary = {"instances": len(rows), "variables_mean": float(np.mean([r["variables"] for r in rows])),
                   "variables_max": int(max(r["variables"] for r in rows))}
        for sweeps in budgets:
            key = "sweeps_%d" % sweeps
            gaps = [r[key]["best_gap_over_spread"] for r in rows if r[key]["best_gap_over_spread"] is not None]
            summary[key] = {
                "success": float(np.mean([r[key]["success"] for r in rows])),
                "best_of_restarts_optimal": float(np.mean([r[key]["best_of_restarts_optimal"] for r in rows])),
                "feasible_share": float(np.mean([r[key]["feasible_share"] for r in rows])),
                "median_best_gap_over_spread": float(np.median(gaps)) if gaps else None,
            }
        summary["instances_detail"] = rows
        out[name] = summary
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--restarts", type=int, default=64)
    parser.add_argument("--sweeps", type=int, default=100)
    parser.add_argument("--scaling-instances", type=int, default=30)
    parser.add_argument("--budgets", type=int, nargs="+", default=[100, 400])
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    sets = p1_2_instances()

    anomaly = part1_anomaly(sets, args.restarts, args.sweeps, rng)
    print("== Part 1: P1.2 anomaly on augmented 2-target scenes ==")
    for key in ("zero_A_crit", "positive_A_crit", "all"):
        g = anomaly[key]
        if g["instances"]:
            print("  %-16s %2d instances   feasible share: P1.2 rule x50 %.3f   safe %.3f"
                  % (key, g["instances"], g["feasible_share_p1_2_rule_x50"], g["feasible_share_safe"]))
        else:
            print("  %-16s  0 instances" % key)

    rules = part2_rules(sets, args.restarts, args.sweeps, rng)
    print("== Part 2: computable rule A = max|c| vs oracle 1.5 x A_crit vs safe ==")
    for name, s in rules.items():
        print("  %s: %d instances (%d with A_crit = 0);  max|c| / A_crit median %s (min %s, max %s)"
              % (name, s["instances"], s["zero_A_crit_instances"],
                 "-" if s["max_abs_over_crit_median"] is None else "%.2f" % s["max_abs_over_crit_median"],
                 "-" if s["max_abs_over_crit_min"] is None else "%.2f" % s["max_abs_over_crit_min"],
                 "-" if s["max_abs_over_crit_max"] is None else "%.2f" % s["max_abs_over_crit_max"]))
        for label, r in s["by_rule"].items():
            if r["success"] is not None:
                print("     %-17s success %.3f   best-of-%d optimal %.3f   feasible %.3f"
                      % (label, r["success"], args.restarts, r["best_of_restarts_optimal"], r["feasible_share"]))

    scaling = part3_scaling(args.scaling_instances, args.restarts, args.budgets, rng)
    print("== Part 3: beyond brute force, A = max|c| ==")
    for name, s in scaling.items():
        print("  %s: %d instances, variables mean %.1f (max %d)" % (name, s["instances"], s["variables_mean"], s["variables_max"]))
        for sweeps in args.budgets:
            r = s["sweeps_%d" % sweeps]
            print("     %4d sweeps: success %.3f   best-of-%d optimal %.3f   feasible %.3f   median best gap/spread %s"
                  % (sweeps, r["success"], args.restarts, r["best_of_restarts_optimal"], r["feasible_share"],
                     "-" if r["median_best_gap_over_spread"] is None else "%.4f" % r["median_best_gap_over_spread"]))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p1_3-annealing-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    out.write_text(json.dumps({
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P1.3 simulated annealing baseline",
        "seed": args.seed,
        "restarts": args.restarts,
        "sweeps_small_instances": args.sweeps,
        "scaling_budgets": args.budgets,
        "schedule": "geometric, T_start = max single-flip |dE|, T_end = 0.05 * cost spread",
        "part1_anomaly": anomaly,
        "part2_rules": rules,
        "part3_scaling": scaling,
    }, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
