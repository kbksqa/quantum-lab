# P2.8 - Closing the open items of P2 (docs/p2-plan.md, Amendment 2): the classical parts O2, O3 and O4.
#
# O3 / H7  Lagrangian relaxation whose recovery may dissolve a relaxed pair (i1, i2) into (i1, 0, 0) and (0, i2, 0)
#          (p2_heuristics.recover, dissolve=True). Scored with the P2.4 checker on all 1,620 benchmark instances, next to
#          the original method, which must reproduce the published baseline table.
# O2 / H6  Marginal likelihood as the tuple cost. The target position is integrated out under a uniform prior over the
#          scene window instead of being replaced by its least-squares fit:
#              c_marg = c_GLR + ln V - 1/2 ln|2 pi P|,   P = (sum_s R_s^-1)^-1,   V = window area
#          The P2.0 singleton rule and the tuple set are kept, so only the costs change.
#          Gate first: the ILP optimum under these costs must equal exact-cover enumeration on tiny scenes.
# O4 / H8  CVaR_0.1 instead of <H> as the QAOA objective on the 30 P2.5 sparse instances, paired against the stored P2.5
#          <H> results, which are re-simulated from their stored angles first.
#
# The grading rules are copied from the amendment.
# The benchmark instance file is read, never rewritten; every instance is regenerated from its seed and compared with it.
#
# Usage:
#     python src/p2_8_followup.py benchmark        # marginal-cost gate, then H7 and H6
#     python src/p2_8_followup.py cvar             # H8

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import json
import math
import time

import numpy as np
from scipy.optimize import minimize
from scipy.stats import binomtest

from p1_5_hardware import distribution_metrics
from p1_qaoa import DEPTHS, interpolate, simulate
from p2_benchmark import ROOT, check, load_instances, make_instance, settings
from p2_heuristics import lagrangian_relaxation, to_builtin
from p2_ilp import enumerate_partitions, solve_ilp
from p2_qaoa import enumerate_strings, max_abs_rule, prepare
from p2_scene import RESULTS, Params, TupleSet, build_tuples, fuse, generate, is_partition, target_cost, truth_partition

BENCHMARK = ROOT / "benchmark" / "p2"
P2_5_FILE = RESULTS / "p2_5-qaoa-20260914-160839.json"
REPLICATES = 3
ALPHA = 0.1
TOL = 1e-6


# ---------------------------------------------------------------- O2: marginal likelihood

def window_area(scene, params) -> float:
    """Area of the P2.0 clutter window: the box around the targets, padded. One constant per scene."""
    low = scene.targets.min(axis=0) - params.window_pad
    high = scene.targets.max(axis=0) + params.window_pad
    area = float(np.prod(high - low))
    if scene.clutter_density > 0 and not math.isclose(area, params.clutter_per_sensor / scene.clutter_density, rel_tol=1e-9):
        raise SystemExit("window area does not match the scene's clutter density - stop")
    return area


def marginal_target_cost(zs: list, Rs: list, n_missing: int, p_detect: float, clutter_density: float, area: float) -> float:
    cost = target_cost(zs, Rs, n_missing, p_detect, clutter_density)
    if math.isinf(cost):
        return cost
    _, P = fuse(zs, Rs)
    return cost + math.log(area) - 0.5 * float(np.linalg.slogdet(2 * math.pi * P)[1])


def marginal_tuple_set(scene, tuple_set, params) -> TupleSet:
    """The same tuples as the GLR set, costed by the marginal likelihood, with the P2.0 singleton rule."""
    area = window_area(scene, params)
    S = len(scene.sensors)
    costs, false_alarm = [], []
    for tup in tuple_set.tuples:
        detected = [s for s in range(S) if tup[s] > 0]
        zs = [scene.measurements[s][tup[s] - 1] for s in detected]
        Rs = [scene.covariances[s][tup[s] - 1] for s in detected]
        cost = marginal_target_cost(zs, Rs, S - len(detected), params.p_detect, scene.clutter_density, area)
        is_false_alarm = False
        if len(detected) == 1 and scene.clutter_density > 0 and cost > 0.0:
            cost, is_false_alarm = 0.0, True
        if math.isinf(cost):
            raise SystemExit("a tuple kept under the GLR cost has an infinite marginal cost - stop")
        costs.append(cost)
        false_alarm.append(is_false_alarm)
    return TupleSet(list(tuple_set.tuples), np.array(costs, dtype=float), false_alarm, dict(tuple_set.counts))


def joined_clutter(scene, partition: list) -> int:
    """Clutter measurements placed in a tuple with two or more measurements."""
    return sum(1 for tup in partition if sum(i > 0 for i in tup) >= 2
               for s, i in enumerate(tup) if i > 0 and scene.origin[s][i - 1] < 0)


GATE_VARIANTS = (
    ("default", {}),
    ("no clutter", {"clutter_per_sensor": 0.0}),
    ("P_D = 1", {"p_detect": 1.0}),
    ("P_D = 0.8, clutter 2", {"p_detect": 0.8, "clutter_per_sensor": 2.0}),
)


def marginal_gate(scenes: int, limit: int, seed: int) -> list:
    rng = np.random.default_rng(seed)
    rows = []
    for name, change in GATE_VARIANTS:
        params = dataclasses.replace(Params(), **change)
        row = {"variant": name, "checked": 0, "skipped_over_limit": 0, "no_valid_partition": 0, "mismatch": 0,
               "max_abs_difference": 0.0}
        for T in (1, 2, 3):
            for _ in range(scenes):
                scene = generate(T, params, rng)
                ts = marginal_tuple_set(scene, build_tuples(scene, params), params)
                ilp = solve_ilp(scene, ts)
                brute = enumerate_partitions(scene, ts, limit)
                if brute is None:
                    row["skipped_over_limit"] += 1
                    continue
                if ilp["status"] not in ("optimal", "empty"):
                    row["no_valid_partition"] += 1
                    row["mismatch"] += int(brute["partitions"] > 0)
                    continue
                row["checked"] += 1
                difference = abs(ilp["cost"] - brute["cost"])
                row["max_abs_difference"] = max(row["max_abs_difference"], difference)
                row["mismatch"] += int(difference > TOL * max(1.0, abs(brute["cost"])) or not is_partition(scene, ilp["partition"]))
        rows.append(row)
    return rows


# ---------------------------------------------------------------- grading

def sign_grade(better: int, worse: int) -> dict:
    """Two-sided sign test. 'held' needs p < 0.05 in the predicted direction; the direction alone is 'partly held'."""
    n = better + worse
    p_value = binomtest(better, n, 0.5).pvalue if n else None
    if better > worse:
        grade = "held" if p_value < 0.05 else "partly held"
    else:
        grade = "failed"
    return {"better": better, "worse": worse, "p_value": p_value, "grade": grade}


def combine(parts: list) -> str:
    if all(p == "held" for p in parts):
        return "held"
    if all(p == "failed" for p in parts):
        return "failed"
    return "partly held"


def h6_verdict(rows: list) -> dict:
    solved = [r for r in rows if r.get("marginal_solved")]
    cluttered = [r for r in solved if r["clutter_per_sensor"] > 0]
    joined = sign_grade(sum(r["marginal_joined_clutter"] < r["glr_joined_clutter"] for r in cluttered),
                        sum(r["marginal_joined_clutter"] > r["glr_joined_clutter"] for r in cluttered))
    truth = sign_grade(sum(r["marginal_equals_truth"] and not r["glr_equals_truth"] for r in solved),
                       sum(r["glr_equals_truth"] and not r["marginal_equals_truth"] for r in solved))
    return {
        "instances_solved": len(solved), "instances_with_clutter": len(cluttered),
        "joined_clutter_total": {"glr": sum(r["glr_joined_clutter"] for r in cluttered),
                                 "marginal": sum(r["marginal_joined_clutter"] for r in cluttered),
                                 "clutter_measurements": sum(r["clutter_measurements"] for r in cluttered)},
        "optimum_equals_truth_share": {"glr": float(np.mean([r["glr_equals_truth"] for r in solved])),
                                       "marginal": float(np.mean([r["marginal_equals_truth"] for r in solved]))},
        "H6a_less_clutter_joined": joined, "H6b_truth_more_often": truth,
        "H6": combine([joined["grade"], truth["grade"]]),
    }


def h7_verdict(rows: list) -> dict:
    feasible = [r for r in rows if r["feasible"]]
    former = [r for r in feasible if not r["lr_original_valid"]]
    lost = [r["id"] for r in feasible if r["lr_original_optimal"] and not r["lr_dissolve_optimal"]]
    still_invalid = [r["id"] for r in feasible if not r["lr_dissolve_valid"]]
    former_optimal = sum(r["lr_dissolve_optimal"] for r in former)
    if still_invalid:
        grade = "failed"
    elif former_optimal >= 8 and not lost:
        grade = "held"
    else:
        grade = "partly held"
    return {
        "feasible_instances": len(feasible),
        "original": {"valid": float(np.mean([r["lr_original_valid"] for r in feasible])),
                     "optimal": float(np.mean([r["lr_original_optimal"] for r in feasible]))},
        "dissolve": {"valid": float(np.mean([r["lr_dissolve_valid"] for r in feasible])),
                     "optimal": float(np.mean([r["lr_dissolve_optimal"] for r in feasible]))},
        "former_failures": [r["id"] for r in former], "former_failures_now_optimal": former_optimal,
        "optimal_before_not_after": lost, "still_without_valid_answer": still_invalid,
        "gained_optimal": [r["id"] for r in feasible if r["lr_dissolve_optimal"] and not r["lr_original_optimal"]],
        "H7": grade,
    }


def breakdown(rows: list) -> list:
    """Exploratory - not part of any verdict: the same measures by clutter and P_D."""
    out = []
    for clutter in (0.0, 0.5, 1.0, 2.0):
        for p_detect in (0.8, 0.9, 1.0):
            group = [r for r in rows if r.get("marginal_solved") and r["clutter_per_sensor"] == clutter
                     and r["p_detect"] == p_detect]
            if not group:
                continue
            out.append({"clutter_per_sensor": clutter, "p_detect": p_detect, "instances": len(group),
                        "glr_equals_truth": float(np.mean([r["glr_equals_truth"] for r in group])),
                        "marginal_equals_truth": float(np.mean([r["marginal_equals_truth"] for r in group])),
                        "glr_joined_clutter": int(sum(r["glr_joined_clutter"] for r in group)),
                        "marginal_joined_clutter": int(sum(r["marginal_joined_clutter"] for r in group)),
                        "lr_original_optimal": float(np.mean([r["lr_original_optimal"] for r in group])),
                        "lr_dissolve_optimal": float(np.mean([r["lr_dissolve_optimal"] for r in group]))})
    return out


# ---------------------------------------------------------------- O2 + O3 on the benchmark

def benchmark_study() -> list:
    stored = {i["id"]: i for i in load_instances(BENCHMARK / "instances.jsonl.gz")}
    with open(BENCHMARK / "baselines.csv", encoding="utf-8") as f:
        published = {r["id"]: r for r in csv.DictReader(f)}
    rows = []
    start = time.perf_counter()
    all_settings = settings()
    for index, setting in enumerate(all_settings):
        for replicate in range(REPLICATES):
            instance, scene, ts, params = make_instance(index, setting, replicate)
            reference = stored[instance["id"]]
            if (instance["tuples"] != reference["tuples"] or instance["costs"] != reference["costs"]
                    or instance["optimum"] != reference["optimum"]):
                raise SystemExit("instance %s does not regenerate as stored - stop" % instance["id"])
            row = {"id": instance["id"], **setting, "feasible": instance["optimum"] is not None,
                   "tuples": len(ts.tuples)}
            if row["feasible"]:
                original = check(instance, lagrangian_relaxation(scene, ts)["partition"])
                dissolved = check(instance, lagrangian_relaxation(scene, ts, dissolve=True)["partition"])
                listed = published[instance["id"]]
                if (original["valid"] != (listed["lagrangian_valid"] == "True")
                        or original["optimal"] != (listed["lagrangian_optimal"] == "True")):
                    raise SystemExit("original Lagrangian result for %s differs from baselines.csv - stop" % instance["id"])
                row.update(lr_original_valid=original["valid"], lr_original_optimal=original["optimal"],
                           lr_dissolve_valid=dissolved["valid"], lr_dissolve_optimal=dissolved["optimal"],
                           lr_dissolve_gap=dissolved["gap_to_optimum"])

                marginal = solve_ilp(scene, marginal_tuple_set(scene, ts, params))
                truth = truth_partition(scene)
                glr_partition = [tuple(t) for t in instance["optimum"]["partition"]]
                row["marginal_solved"] = marginal["status"] in ("optimal", "empty")
                if row["marginal_solved"]:
                    row.update(glr_equals_truth=glr_partition == truth,
                               marginal_equals_truth=marginal["partition"] == truth,
                               same_partition=marginal["partition"] == glr_partition,
                               glr_joined_clutter=joined_clutter(scene, glr_partition),
                               marginal_joined_clutter=joined_clutter(scene, marginal["partition"]),
                               clutter_measurements=sum(o < 0 for per in scene.origin for o in per))
            rows.append(row)
        if (index + 1) % 60 == 0:
            print("  %d / %d settings, %.0f s" % (index + 1, len(all_settings), time.perf_counter() - start), flush=True)
    return rows


# ---------------------------------------------------------------- O4: CVaR objective

def cvar(probs: np.ndarray, energies: np.ndarray, alpha: float) -> float:
    """Mean energy of the lowest-energy alpha share of the distribution, including the boundary energy's fraction."""
    order = np.argsort(energies, kind="stable")
    p, e = probs[order], energies[order]
    before = np.cumsum(p) - p
    weights = np.clip(alpha - before, 0.0, p)
    return float(weights @ e / weights.sum())


def optimize_cvar(diag: np.ndarray, m: int, p: int, rng, starts: int, warm, alpha: float) -> tuple[np.ndarray, float]:
    """p1_qaoa.optimize with CVaR_alpha as the objective; starts, ranges and COBYLA options unchanged."""
    def objective(v):
        return cvar(simulate(diag, m, v[:p], v[p:]), diag, alpha)

    initial = [np.concatenate([rng.uniform(0, math.pi, p), rng.uniform(0, math.pi / 2, p)]) for _ in range(starts)]
    if warm is not None:
        initial.insert(0, warm)
    best = None
    for x0 in initial:
        res = minimize(objective, x0, method="COBYLA", options={"maxiter": 300, "rhobeg": 0.3})
        if best is None or res.fun < best.fun:
            best = res
    return np.asarray(best.x), float(best.fun)


def cvar_study(starts: int, seed: int) -> list:
    from p2_6_hardware import rebuild_sparse

    stored = json.loads(P2_5_FILE.read_text(encoding="utf-8"))
    detail = stored["sets"]["sparse T=2"]["instances_detail"]
    rng = np.random.default_rng(seed)
    rows = []
    for index, ((scene, ts), record) in enumerate(zip(rebuild_sparse(stored), detail)):
        optimum = solve_ilp(scene, ts)["cost"]
        if abs(optimum - record["optimum"]) > 1e-9 or len(ts.tuples) != record["variables"]:
            raise SystemExit("rebuilt sparse instance %d does not match P2.5 - stop" % index)
        strings = enumerate_strings(scene, ts)
        A, _ = max_abs_rule(ts)
        if abs(A - record["qaoa"]["max_abs"]["A"]) > 1e-12:
            raise SystemExit("penalty of sparse instance %d does not match P2.5 - stop" % index)
        prep = prepare(scene, ts, A, strings)
        m = len(prep["h"])
        row = {"index": index, "variables": m, "uniform_p_optimal": record["uniform_p_optimal"], "depths": {}}
        warm = None
        for p in DEPTHS:
            key = "p%d" % p
            reference = record["qaoa"]["max_abs"][key]
            again = distribution_metrics(simulate(prep["diag"], m, reference["gammas"], reference["betas"]), strings, optimum)
            if abs(again["p_optimal"] - reference["p_optimal"]) > 1e-9:
                raise SystemExit("stored <H> angles do not reproduce P2.5 for sparse instance %d at %s - stop" % (index, key))
            params, value = optimize_cvar(prep["diag"], m, p, rng, starts, warm, ALPHA)
            found = distribution_metrics(simulate(prep["diag"], m, params[:p], params[p:]), strings, optimum)
            row["depths"][key] = {
                "cvar_p_optimal": found["p_optimal"], "cvar_p_feasible": found["p_feasible"],
                "expectation_p_optimal": reference["p_optimal"], "expectation_p_feasible": again["p_feasible"],
                "difference": found["p_optimal"] - reference["p_optimal"],
                "cvar_scaled": value, "gammas": params[:p].tolist(), "betas": params[p:].tolist(),
            }
            warm = interpolate(params, p, p + 1)
        rows.append(row)
        print("  instance %2d (%2d qubits): %s" % (index, m, "  ".join(
            "%s %.4f vs %.4f" % (k, d["cvar_p_optimal"], d["expectation_p_optimal"]) for k, d in row["depths"].items())),
            flush=True)
    return rows


def h8_verdict(rows: list) -> dict:
    depths = {}
    for p in DEPTHS:
        key = "p%d" % p
        diffs = np.array([r["depths"][key]["difference"] for r in rows])
        depths[key] = {"n": len(diffs), "mean_difference": float(diffs.mean()),
                       "sem": float(diffs.std(ddof=1) / math.sqrt(len(diffs))),
                       "positive_share": float(np.mean(diffs > 0)),
                       "cvar_p_optimal_mean": float(np.mean([r["depths"][key]["cvar_p_optimal"] for r in rows])),
                       "expectation_p_optimal_mean": float(np.mean([r["depths"][key]["expectation_p_optimal"] for r in rows])),
                       "cvar_p_feasible_mean": float(np.mean([r["depths"][key]["cvar_p_feasible"] for r in rows])),
                       "expectation_p_feasible_mean": float(np.mean([r["depths"][key]["expectation_p_feasible"] for r in rows]))}
    positive_all = all(d["mean_difference"] > 0 for d in depths.values())
    strong_p1 = depths["p1"]["mean_difference"] > 2 * depths["p1"]["sem"]
    if positive_all and strong_p1:
        grade = "held"
    elif depths["p1"]["mean_difference"] > 0:
        grade = "partly held"
    else:
        grade = "failed"
    return {"alpha": ALPHA, "depths": depths, "uniform_p_optimal_mean": float(np.mean([r["uniform_p_optimal"] for r in rows])),
            "H8": grade}


# ---------------------------------------------------------------- main

def save(name: str, record: dict) -> None:
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p2_8-%s-%s.json" % (name, dt.datetime.now().strftime("%Y%m%d-%H%M%S")))
    out.write_text(json.dumps(record, indent=2, default=to_builtin), encoding="utf-8")
    print("saved " + str(out))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("benchmark")
    b.add_argument("--gate-scenes", type=int, default=50)
    b.add_argument("--limit", type=int, default=200_000)
    b.add_argument("--seed", type=int, default=2037)
    c = sub.add_parser("cvar")
    c.add_argument("--starts", type=int, default=6)
    c.add_argument("--seed", type=int, default=2038)
    args = parser.parse_args()
    stamp = dt.datetime.now().astimezone().isoformat()

    if args.command == "benchmark":
        print("gate: ILP under the marginal cost vs exact-cover enumeration, T = 1..3")
        gate = marginal_gate(args.gate_scenes, args.limit, args.seed)
        for row in gate:
            print("  %s" % row)
        if any(row["mismatch"] for row in gate):
            save("marginal-gate-failed", {"timestamp": stamp, "gate": gate})
            raise SystemExit("GATE FAILED - the benchmark study does not run")
        print("gate passed; scoring the 1,620 benchmark instances")
        rows = benchmark_study()
        h7, h6 = h7_verdict(rows), h6_verdict(rows)
        print("H7: %s" % {k: v for k, v in h7.items() if k not in ("former_failures", "gained_optimal")})
        print("H6: %s" % h6)
        save("benchmark", {"timestamp": stamp, "experiment": "P2.8 O2 (H6) and O3 (H7) on the P2 benchmark",
                           "gate_seed": args.seed, "gate": gate, "h7_verdict": h7, "h6_verdict": h6,
                           "exploratory_breakdown": breakdown(rows), "instances": rows})
    else:
        rows = cvar_study(args.starts, args.seed)
        h8 = h8_verdict(rows)
        print("H8: %s" % h8)
        save("cvar", {"timestamp": stamp, "experiment": "P2.8 O4 (H8): CVaR objective on the P2.5 sparse instances",
                      "seed": args.seed, "starts": args.starts, "alpha": ALPHA, "h8_verdict": h8, "instances": rows})


if __name__ == "__main__":
    main()
