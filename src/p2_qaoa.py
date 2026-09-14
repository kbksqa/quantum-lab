# P2.5 - QAOA on a simulator for the smallest multi-sensor assignment QUBOs: H3 and the hardware go/no-go.
#
# Instance sets, fixed before running:
#   "pure T=2"   P_D = 1, no clutter, no gate, 2 targets: always 8 tuples = 8 qubits. 30 instances.
#   "sparse T=2" default parameters with bearing error 0.005 rad, 2 targets, kept only when the ILP has an optimum and
#                6 <= tuples <= 12. 30 instances; rejected scenes are counted by reason.
# Per instance: every 2^K bit string enumerated; exact critical penalty A_crit as in P1.2; simulated annealing (P1 routine,
# 64 restarts x 100 sweeps) at A = s x A_crit, at A = max(max|c|, 1) and at the safe penalty; QAOA at depths 1-3 with
# A = max(max|c|, 1) and A = 1.5 x A_crit (P1.4 simulator, COBYLA, 6 random starts plus an interpolated start).
#
# H3 as registered: "annealing does best near the exact critical penalty, while QAOA does better with A = max|c| than with
# 1.5 x A_crit - the P1 result replicates". Made operational here, written before the first run:
#   - annealing part: among A = s x A_crit with s in {1.1, 1.5, 2, 5, 10, 50}, the s with the highest mean success is <= 2,
#     in both sets
#   - QAOA part: the mean paired difference P(opt | max|c|) - P(opt | 1.5 A_crit) is positive at p = 1, 2 and 3 and larger
#     than 2 standard errors at p = 3, in both sets. Positive at p = 3 in both sets without meeting the rest: partly held
#   - each part: held / partly held / failed; overall: held if both hold, failed if both fail, partly held otherwise
#   - instances with A_crit = 0 have no usable oracle penalty; they are counted and left out of both parts
#   - A = max|c| gets a floor of 1, the P2.2 finding; the floor is counted whenever it is used
#
# Hardware go/no-go (plan): go only if some set, penalty rule and depth reaches mean P(opt) >= 5 x mean uniform P(opt) with
# a median estimated two-qubit gate count <= 60 (heavy-hex CZ model, first 5 instances of the set). Otherwise no QPU time
# is spent on three-dimensional QAOA.
#
# Usage:
#     python src/p2_qaoa.py
#     python src/p2_qaoa.py --instances 50 --starts 6

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math

import numpy as np

from p1_penalty import MULTIPLIERS, anneal, critical_penalty
from p1_qaoa import DEPTHS, evaluate, interpolate, ising, ising_energies, optimize, resources, simulate
from p2_ilp import cover_matrix, solve_ilp
from p2_qubo import build_qubo, safe_penalty
from p2_scene import PURE, RESULTS, Params, build_tuples, generate

RESOURCE_INSTANCES = 5


def enumerate_strings(scene, tuple_set) -> dict:
    K = len(tuple_set.tuples)
    A = cover_matrix(scene, tuple_set).toarray().astype(np.int32)
    idx = np.arange(1 << K, dtype=np.int64)
    X = ((idx[:, None] >> np.arange(K)) & 1).astype(np.int16)
    cover = X.astype(np.int32) @ A.T
    return {"X": X, "cost": X.astype(float) @ np.asarray(tuple_set.costs, dtype=float),
            "V": ((cover - 1) ** 2).sum(axis=1)}


def max_abs_rule(tuple_set) -> tuple[float, bool]:
    value = float(np.max(np.abs(tuple_set.costs)))
    return max(value, 1.0), value < 1.0


def prepare(scene, tuple_set, A: float, strings: dict) -> dict:
    qubo = build_qubo(scene, tuple_set, penalty=A)
    h, J, const = ising(qubo)
    scale = max(float(np.abs(h).max()), max((abs(v) for v in J.values()), default=0.0))
    energies = strings["cost"] + A * strings["V"]
    if not np.allclose(ising_energies(h, J, const, strings["X"]), energies, atol=1e-8 * max(1.0, float(np.abs(energies).max()))):
        raise SystemExit("Ising conversion does not reproduce the enumerated energies - stop")
    return {"qubo": qubo, "h": h, "J": J, "const": const, "scale": scale, "energies": energies,
            "diag": (energies - const) / scale}


def anneal_success(qubo: dict, strings_optimal: np.ndarray, rng, restarts: int, sweeps: int) -> float:
    states = anneal(qubo, restarts, sweeps, rng)
    index = states @ (1 << np.arange(states.shape[1], dtype=np.int64))
    return float(strings_optimal[index].mean())


def pure_set(n: int, rng) -> tuple[list, dict]:
    params = dataclasses.replace(Params(), **PURE)
    out = []
    for _ in range(n):
        scene = generate(2, params, rng)
        out.append((scene, build_tuples(scene, params)))
    return out, {"generated": n}


def sparse_set(n: int, rng) -> tuple[list, dict]:
    params = dataclasses.replace(Params(), sigma_bearing=0.005)
    out, counts = [], {"generated": 0, "rejected_no_optimum": 0, "rejected_fewer_than_6": 0, "rejected_more_than_12": 0}
    while len(out) < n:
        scene = generate(2, params, rng)
        ts = build_tuples(scene, params)
        counts["generated"] += 1
        K = len(ts.tuples)
        if K < 6:
            counts["rejected_fewer_than_6"] += 1
        elif K > 12:
            counts["rejected_more_than_12"] += 1
        elif solve_ilp(scene, ts)["status"] != "optimal":
            counts["rejected_no_optimum"] += 1
        else:
            out.append((scene, ts))
    return out, counts


def paired(rows: list, depth: str) -> dict:
    diffs = np.array([r["qaoa"]["max_abs"][depth]["p_optimal"] - r["qaoa"]["oracle_1.5x_crit"][depth]["p_optimal"]
                      for r in rows if "oracle_1.5x_crit" in r["qaoa"]])
    if len(diffs) < 2:
        return {"n": int(len(diffs)), "mean": float(diffs.mean()) if len(diffs) else None, "sem": None}
    return {"n": int(len(diffs)), "mean": float(diffs.mean()), "sem": float(diffs.std(ddof=1) / math.sqrt(len(diffs))),
            "positive_share": float(np.mean(diffs > 0))}


def run_set(label: str, instances: list, starts: int, shots: int, restarts: int, sweeps: int, seed: int) -> dict:
    sa_rng = np.random.default_rng([seed, 1])
    qaoa_rng = np.random.default_rng([seed, 2])
    rows, resource_rows = [], {}
    floor_used = 0
    for index, (scene, ts) in enumerate(instances):
        optimum = solve_ilp(scene, ts)["cost"]
        strings = enumerate_strings(scene, ts)
        feasible = strings["V"] == 0
        optimal = feasible & (np.abs(strings["cost"] - optimum) <= 1e-6 * max(1.0, abs(optimum)))
        a_crit = critical_penalty(strings, optimum)
        A_max, floored = max_abs_rule(ts)
        floor_used += floored
        row = {"index": index, "variables": len(ts.tuples), "optimum": optimum, "A_crit": a_crit, "A_max_abs": A_max,
               "max_abs_floor_used": floored, "uniform_p_optimal": float(optimal.mean()), "annealing": {}, "qaoa": {}}

        penalties = {"max_abs": A_max, "safe": safe_penalty(ts.costs)}
        if a_crit > 0:
            penalties.update({"%gx_crit" % s: s * a_crit for s in MULTIPLIERS})
        for name, A in penalties.items():
            row["annealing"][name] = {"A": A, "success": anneal_success(build_qubo(scene, ts, penalty=A), optimal,
                                                                        sa_rng, restarts, sweeps)}

        rules = {"max_abs": A_max}
        if a_crit > 0:
            rules["oracle_1.5x_crit"] = 1.5 * a_crit
        for rule, A in rules.items():
            prep = prepare(scene, ts, A, strings)
            m = len(prep["h"])
            warm, per_depth = None, {}
            for p in DEPTHS:
                params, expectation = optimize(prep["diag"], m, p, qaoa_rng, starts, warm)
                probs = simulate(prep["diag"], m, params[:p], params[p:])
                result = evaluate(probs, strings, optimum, shots, qaoa_rng)
                result.update({"expectation_scaled": expectation, "gammas": params[:p].tolist(), "betas": params[p:].tolist()})
                if index < RESOURCE_INSTANCES:
                    result["resources"] = resources(prep, params, p)
                per_depth["p%d" % p] = result
                warm = interpolate(params, p, p + 1)
            row["qaoa"][rule] = {"A": A, **per_depth}
        rows.append(row)

    with_oracle = [r for r in rows if r["A_crit"] > 0]
    annealing_means = {"%gx_crit" % s: float(np.mean([r["annealing"]["%gx_crit" % s]["success"] for r in with_oracle]))
                       for s in MULTIPLIERS} if with_oracle else {}
    for name in ("max_abs", "safe"):
        annealing_means[name] = float(np.mean([r["annealing"][name]["success"] for r in rows]))
    best_multiplier = max(MULTIPLIERS, key=lambda s: annealing_means["%gx_crit" % s]) if with_oracle else None

    qaoa_means, cz = {}, {}
    for rule in ("max_abs", "oracle_1.5x_crit"):
        present = [r for r in rows if rule in r["qaoa"]]
        for p in DEPTHS:
            key = "p%d" % p
            qaoa_means["%s %s" % (rule, key)] = {
                "n": len(present),
                "p_optimal_mean": float(np.mean([r["qaoa"][rule][key]["p_optimal"] for r in present])) if present else None,
                "p_feasible_mean": float(np.mean([r["qaoa"][rule][key]["p_feasible"] for r in present])) if present else None,
                "uniform_p_optimal_mean": float(np.mean([r["uniform_p_optimal"] for r in present])) if present else None,
            }
            counts = [r["qaoa"][rule][key]["resources"]["two_qubit_gates"] for r in present if "resources" in r["qaoa"][rule][key]]
            cz["%s %s" % (rule, key)] = float(np.median(counts)) if counts else None
    return {
        "label": label, "instances": len(rows), "A_crit_zero": len(rows) - len(with_oracle), "max_abs_floor_used": floor_used,
        "variables_mean": float(np.mean([r["variables"] for r in rows])),
        "annealing_success_mean": annealing_means, "annealing_best_multiplier": best_multiplier,
        "qaoa": qaoa_means, "median_cz_first_instances": cz,
        "paired_max_abs_minus_oracle": {"p%d" % p: paired(rows, "p%d" % p) for p in DEPTHS},
        "instances_detail": rows,
    }


def h3_verdict(sets: dict) -> dict:
    def grade(held: bool, partly: bool) -> str:
        return "held" if held else ("partly held" if partly else "failed")

    anneal_ok = [s["annealing_best_multiplier"] is not None and s["annealing_best_multiplier"] <= 2 for s in sets.values()]
    annealing = grade(all(anneal_ok), any(anneal_ok))

    def qaoa_ok(s):
        d = s["paired_max_abs_minus_oracle"]
        if any(d[k]["mean"] is None for k in d):
            return False, False
        positive_all = all(d[k]["mean"] > 0 for k in d)
        strong = d["p3"]["sem"] is not None and d["p3"]["mean"] > 2 * d["p3"]["sem"]
        return positive_all and strong, d["p3"]["mean"] > 0

    results = [qaoa_ok(s) for s in sets.values()]
    qaoa = grade(all(r[0] for r in results), all(r[1] for r in results))
    parts = [annealing, qaoa]
    overall = "held" if parts == ["held", "held"] else ("failed" if parts == ["failed", "failed"] else "partly held")
    return {"annealing_best_near_A_crit": annealing, "qaoa_prefers_max_abs": qaoa, "H3": overall}


def go_no_go(sets: dict) -> dict:
    candidates = []
    for s in sets.values():
        for key, q in s["qaoa"].items():
            if q["p_optimal_mean"] is None:
                continue
            ratio = q["p_optimal_mean"] / q["uniform_p_optimal_mean"]
            cz = s["median_cz_first_instances"][key]
            candidates.append({"set": s["label"], "rule_depth": key, "ratio_to_guessing": ratio, "median_cz": cz,
                               "passes": ratio >= 5 and cz is not None and cz <= 60})
    return {"go": any(c["passes"] for c in candidates), "candidates": candidates}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", type=int, default=30)
    parser.add_argument("--starts", type=int, default=6)
    parser.add_argument("--shots", type=int, default=1024)
    parser.add_argument("--restarts", type=int, default=64)
    parser.add_argument("--sweeps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2032)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    pure, pure_counts = pure_set(args.instances, rng)
    sparse, sparse_counts = sparse_set(args.instances, rng)
    sets = {
        "pure T=2": run_set("pure T=2", pure, args.starts, args.shots, args.restarts, args.sweeps, args.seed + 10),
        "sparse T=2": run_set("sparse T=2", sparse, args.starts, args.shots, args.restarts, args.sweeps, args.seed + 20),
    }
    sets["pure T=2"]["selection"] = pure_counts
    sets["sparse T=2"]["selection"] = sparse_counts

    for s in sets.values():
        print("== %s: %d instances, variables mean %.1f, A_crit = 0 in %d, max|c| floor used %d, selection %s =="
              % (s["label"], s["instances"], s["variables_mean"], s["A_crit_zero"], s["max_abs_floor_used"], s["selection"]))
        print("   annealing mean success: %s  (best multiplier %s)"
              % ({k: round(v, 3) for k, v in s["annealing_success_mean"].items()}, s["annealing_best_multiplier"]))
        for key, q in s["qaoa"].items():
            print("   QAOA %-22s n %2d  P(opt) %.4f  P(feasible) %.4f  uniform %.4f  x%.1f  median CZ %s"
                  % (key, q["n"], q["p_optimal_mean"] or 0, q["p_feasible_mean"] or 0, q["uniform_p_optimal_mean"] or 0,
                     (q["p_optimal_mean"] or 0) / (q["uniform_p_optimal_mean"] or 1), s["median_cz_first_instances"][key]))
        for p, d in s["paired_max_abs_minus_oracle"].items():
            print("   paired max|c| - 1.5 A_crit at %s: %s" % (p, d))
    verdict = h3_verdict(sets)
    decision = go_no_go(sets)
    print("H3: %s" % verdict)
    print("hardware go/no-go: %s" % ("GO" if decision["go"] else "NO-GO"))
    for c in decision["candidates"]:
        print("   %-10s %-22s x%.1f guessing, median CZ %s, passes %s"
              % (c["set"], c["rule_depth"], c["ratio_to_guessing"], c["median_cz"], c["passes"]))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p2_5-qaoa-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps({
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P2.5 QAOA on a simulator, H3 and hardware go/no-go",
        "seed": args.seed, "starts": args.starts, "shots": args.shots, "depths": DEPTHS,
        "annealing": {"restarts": args.restarts, "sweeps": args.sweeps, "multipliers": MULTIPLIERS},
        "resources_note": "heavy-hex (distance 3) CZ model via GenericBackendV2, optimization_level 3 - an estimate, "
                          "median over the first %d instances" % RESOURCE_INSTANCES,
        "h3_verdict": verdict, "go_no_go": decision, "sets": sets,
    }, indent=2, default=lambda v: v.item() if isinstance(v, np.generic) else str(v)), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
