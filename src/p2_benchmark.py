# P2.4 - Reproducible benchmark for multi-sensor data association: instance files, a checker and a baseline table.
#
# Sweep (plan + amendment 1): targets 2..6 x clutter per sensor 0, 0.5, 1, 2 x P_D 0.8, 0.9, 1.0 x spacing 25, 50, 100 m
# x bearing error 0.005, 0.01, 0.02 rad = 540 settings, a few replicates each. Every instance has its own seed
# [2031, setting index, replicate], so any single instance can be regenerated without the others.
#
# Each instance (one JSON object per line) holds: the generator seed and parameters, sensor positions, measurements with
# covariances, the true association, every allowed tuple with its cost, the exact optimum (ILP), the LP bound and gap flag.
#
# The checker needs only an instance and a proposed partition - no generator, no solver - so any method, classical or
# quantum, is scored the same way: validity, cost, gap to the optimum, and agreement with the truth.
# Baselines are scored through the same checker.
#
# Usage:
#     python src/p2_benchmark.py build                         # instances + baselines + summary into benchmark/p2/
#     python src/p2_benchmark.py build --replicates 1 --max-settings 20 --out <dir>   # quick trial
#     python src/p2_benchmark.py check benchmark/p2/instances.jsonl.gz answers.json
#
# answers.json: {"<instance id>": [[i1, i2, i3], ...], ...} - measurement indices are 1-based per sensor, 0 = not seen.

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import gzip
import itertools
import json
import math
import pathlib
import time

import numpy as np

FORMAT = "quantum-lab P2 multi-sensor assignment instance v1"
BASE_SEED = 2031
SWEEP = {
    "targets": [2, 3, 4, 5, 6],
    "clutter_per_sensor": [0.0, 0.5, 1.0, 2.0],
    "p_detect": [0.8, 0.9, 1.0],
    "spacing": [25.0, 50.0, 100.0],
    "sigma_bearing": [0.005, 0.01, 0.02],
}
ROOT = pathlib.Path(__file__).resolve().parents[1]
TOL = 1e-6


# ---------------------------------------------------------------- checker (standard library only)

def load_instances(path) -> list:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def check(instance: dict, answer) -> dict:
    """Score a proposed partition against one instance. Uses only the instance's own data."""
    tuples = [tuple(t) for t in instance["tuples"]]
    lookup = dict(zip(tuples, instance["costs"]))
    S = len(instance["sensors"])
    sizes = [len(m) for m in instance["measurements"]]
    problems = []
    proposed = []
    for raw in answer or []:
        tup = tuple(int(i) for i in raw)
        if len(tup) != S or not any(tup) or any(i < 0 or i > sizes[s] for s, i in enumerate(tup)):
            problems.append("malformed tuple %s" % (list(raw),))
            continue
        if tup not in lookup:
            problems.append("tuple %s is not an allowed tuple" % (list(tup),))
        proposed.append(tup)
    cover = {(s, j): 0 for s in range(S) for j in range(1, sizes[s] + 1)}
    for tup in proposed:
        for s, i in enumerate(tup):
            if i > 0:
                cover[s, i] += 1
    for (s, j), n in cover.items():
        if n != 1:
            problems.append("sensor %d measurement %d used %d times" % (s + 1, j, n))

    optimum = instance["optimum"]["cost"] if instance["optimum"] else None
    truth = {tuple(t) for t in instance["truth"]["partition"]}
    result = {"valid": not problems, "problems": problems[:10], "cost": None, "gap_to_optimum": None, "optimal": False,
              "equals_truth": False, "truth_tuples_recovered": None}
    if problems:
        return result
    cost = float(sum(lookup[t] for t in proposed))
    result.update(cost=cost, equals_truth=set(proposed) == truth,
                  truth_tuples_recovered=len(set(proposed) & truth) / len(truth) if truth else 1.0)
    if optimum is not None:
        result["gap_to_optimum"] = cost - optimum
        result["optimal"] = abs(cost - optimum) <= TOL * max(1.0, abs(optimum))
    return result


# ---------------------------------------------------------------- building

def settings() -> list:
    keys = list(SWEEP)
    return [dict(zip(keys, values)) for values in itertools.product(*SWEEP.values())]


def make_instance(index: int, setting: dict, replicate: int) -> tuple[dict, object, object, object]:
    from p2_ilp import lp_relaxation, solve_ilp
    from p2_scene import Params, build_tuples, generate, truth_partition

    change = {k: v for k, v in setting.items() if k != "targets"}
    params = dataclasses.replace(Params(), **change)
    seed = [BASE_SEED, index, replicate]
    scene = generate(setting["targets"], params, np.random.default_rng(seed))
    ts = build_tuples(scene, params)
    ilp = solve_ilp(scene, ts)
    feasible = ilp["status"] in ("optimal", "empty")
    lp = lp_relaxation(scene, ts) if feasible else {"bound": None}
    optimum = ilp["cost"] if feasible else None
    instance = {
        "id": "p2-%03d-%d" % (index, replicate),
        "format": FORMAT,
        "generator": {"code": "src/p2_scene.py", "seed": seed, "targets": setting["targets"],
                      "params": dataclasses.asdict(params)},
        "sensors": scene.sensors.tolist(),
        "clutter_density": scene.clutter_density,
        "measurements": [m.tolist() for m in scene.measurements],
        "covariances": [c.tolist() for c in scene.covariances],
        "truth": {"targets": scene.targets.tolist(), "origin": scene.origin,
                  "partition": [list(t) for t in truth_partition(scene)]},
        "tuples": [list(t) for t in ts.tuples],
        "costs": ts.costs.tolist(),
        "false_alarm": list(ts.false_alarm),
        "tuple_counts": ts.counts,
        "optimum": {"cost": optimum, "partition": [list(t) for t in ilp["partition"]]} if feasible else None,
        "lp_bound": lp["bound"],
        "has_gap": bool(feasible and optimum - lp["bound"] > TOL * max(1.0, abs(optimum))),
    }
    return instance, scene, ts, params


def run_baselines(instance: dict, scene, ts, params, index: int, replicate: int, restarts: int, sweeps: int) -> dict:
    from p2_heuristics import greedy, greedy_normalised, lagrangian_relaxation
    from p2_qubo import build_qubo, decode
    from p1_penalty import anneal

    out = {}
    if instance["optimum"] is None:
        return out

    def timed(fn):
        start = time.perf_counter()
        partition = fn()
        return partition, time.perf_counter() - start

    def sa_best():
        penalty = max(float(np.max(np.abs(ts.costs))), 1.0) if len(ts.costs) else 1.0
        qubo = build_qubo(scene, ts, penalty=penalty)
        best, best_cost = None, math.inf
        for x in anneal(qubo, restarts, sweeps, np.random.default_rng([BASE_SEED, index, replicate, 1])):
            ok, partition = decode(x, qubo, scene)
            if ok:
                cost = float(sum(c for bit, c in zip(x, ts.costs) if bit))
                if cost < best_cost:
                    best, best_cost = partition, cost
        return best

    methods = {
        "greedy": lambda: greedy(scene, ts)["partition"],
        "greedy_normalised": lambda: greedy_normalised(scene, ts, params.p_detect)["partition"],
        "lagrangian": lambda: lagrangian_relaxation(scene, ts)["partition"],
        "annealing": sa_best,
    }
    for name, fn in methods.items():
        if name == "annealing" and not ts.tuples:
            partition, seconds = [], 0.0
        else:
            partition, seconds = timed(fn)
        score = check(instance, partition)
        score["seconds"] = seconds
        out[name] = score
    return out


METHODS = ("greedy", "greedy_normalised", "lagrangian", "annealing")


def summary_tables(rows: list) -> str:
    lines = []
    solved = [r for r in rows if r["feasible"]]
    lines.append("| | instances | infeasible | with LP gap | optimum = truth | tuples mean / max |")
    lines.append("|---|---|---|---|---|---|")
    lines.append("| all | %d | %d | %.3f | %.3f | %.1f / %d |" % (
        len(rows), len(rows) - len(solved), np.mean([r["has_gap"] for r in solved]),
        np.mean([r["optimum_equals_truth"] for r in solved]), np.mean([r["tuples"] for r in rows]),
        max(r["tuples"] for r in rows)))
    lines.append("")
    for factor in SWEEP:
        lines.append("### by %s" % factor)
        lines.append("")
        lines.append("| %s | instances | infeasible | with gap | optimum = truth | %s |" % (
            factor, " | ".join("%s optimal" % m for m in METHODS)))
        lines.append("|" + "---|" * (5 + len(METHODS)))
        for value in SWEEP[factor]:
            group = [r for r in rows if r["setting"][factor] == value]
            ok = [r for r in group if r["feasible"]]
            cells = ["%.3f" % np.mean([r[m + "_optimal"] for r in ok]) if ok else "-" for m in METHODS]
            lines.append("| %s | %d | %d | %.3f | %.3f | %s |" % (
                value, len(group), len(group) - len(ok), np.mean([r["has_gap"] for r in ok]) if ok else 0,
                np.mean([r["optimum_equals_truth"] for r in ok]) if ok else 0, " | ".join(cells)))
        lines.append("")
    lines.append("### methods, all solvable instances")
    lines.append("")
    lines.append("| method | valid | optimal | median gap when not optimal | median seconds | max seconds |")
    lines.append("|---|---|---|---|---|---|")
    for m in METHODS:
        gaps = [r[m + "_gap"] for r in solved if r[m + "_valid"] and not r[m + "_optimal"]]
        lines.append("| %s | %.3f | %.3f | %s | %.4f | %.3f |" % (
            m, np.mean([r[m + "_valid"] for r in solved]), np.mean([r[m + "_optimal"] for r in solved]),
            "%.3f" % np.median(gaps) if gaps else "-", np.median([r[m + "_seconds"] for r in solved]),
            max(r[m + "_seconds"] for r in solved)))
    return "\n".join(lines) + "\n"


def build(args) -> None:
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_settings = settings()[: args.max_settings] if args.max_settings else settings()
    rows = []
    start = time.perf_counter()
    with gzip.open(out_dir / "instances.jsonl.gz", "wt", encoding="utf-8") as f:
        for index, setting in enumerate(all_settings):
            for replicate in range(args.replicates):
                instance, scene, ts, params = make_instance(index, setting, replicate)
                f.write(json.dumps(instance, separators=(",", ":")) + "\n")
                scores = run_baselines(instance, scene, ts, params, index, replicate, args.restarts, args.sweeps)
                feasible = instance["optimum"] is not None
                row = {"id": instance["id"], "setting": setting, "feasible": feasible, "tuples": len(ts.tuples),
                       "has_gap": instance["has_gap"],
                       "optimum_equals_truth": feasible and check(instance, instance["optimum"]["partition"])["equals_truth"],
                       "optimum": instance["optimum"]["cost"] if feasible else None, "lp_bound": instance["lp_bound"]}
                for m in METHODS:
                    s = scores.get(m, {})
                    row.update({m + "_valid": s.get("valid", False), m + "_optimal": s.get("optimal", False),
                                m + "_gap": s.get("gap_to_optimum"), m + "_equals_truth": s.get("equals_truth", False),
                                m + "_seconds": s.get("seconds")})
                rows.append(row)
            if (index + 1) % 60 == 0:
                print("  %d / %d settings, %.0f s" % (index + 1, len(all_settings), time.perf_counter() - start), flush=True)

    with open(out_dir / "baselines.csv", "w", newline="", encoding="utf-8") as f:
        fields = ["id"] + list(SWEEP) + [k for k in rows[0] if k not in ("id", "setting")]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({"id": r["id"], **r["setting"], **{k: v for k, v in r.items() if k not in ("id", "setting")}})

    tables = summary_tables(rows)
    header = ("# P2 benchmark - baseline summary\n\nGenerated by `python src/p2_benchmark.py build` on %s.\n"
              "%d settings x %d replicates = %d instances. Annealing: %d restarts, %d sweeps, best valid restart kept.\n\n"
              % (dt.date.today().isoformat(), len(all_settings), args.replicates, len(rows), args.restarts, args.sweeps))
    (out_dir / "summary.md").write_text(header + tables, encoding="utf-8")
    manifest = {
        "format": FORMAT, "built": dt.datetime.now().astimezone().isoformat(), "base_seed": BASE_SEED, "sweep": SWEEP,
        "settings": len(all_settings), "replicates": args.replicates, "instances": len(rows),
        "annealing": {"restarts": args.restarts, "sweeps": args.sweeps}, "seconds": time.perf_counter() - start,
        "hard_subset_lp_gap": [r["id"] for r in rows if r["has_gap"]],
        "hard_subset_lagrangian_not_optimal": [r["id"] for r in rows if r["feasible"] and not r["lagrangian_optimal"]],
        "infeasible": [r["id"] for r in rows if not r["feasible"]],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(tables)
    print("saved to %s in %.0f s" % (out_dir, time.perf_counter() - start))


def check_cli(args) -> None:
    instances = {i["id"]: i for i in load_instances(args.instances)}
    answers = json.loads(pathlib.Path(args.answers).read_text(encoding="utf-8"))
    scored = {key: check(instances[key], value) for key, value in answers.items() if key in instances}
    unknown = [key for key in answers if key not in instances]
    valid = sum(s["valid"] for s in scored.values())
    optimal = sum(s["optimal"] for s in scored.values())
    print("answers %d  unknown ids %d  valid %d  optimal %d" % (len(answers), len(unknown), valid, optimal))
    if args.details:
        pathlib.Path(args.details).write_text(json.dumps(scored, indent=2), encoding="utf-8")
        print("details saved to " + args.details)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--replicates", type=int, default=3)
    b.add_argument("--max-settings", type=int, default=0)
    b.add_argument("--restarts", type=int, default=64)
    b.add_argument("--sweeps", type=int, default=100)
    b.add_argument("--out", default=str(ROOT / "benchmark" / "p2"))
    c = sub.add_parser("check")
    c.add_argument("instances")
    c.add_argument("answers")
    c.add_argument("--details", default=None)
    args = parser.parse_args()
    build(args) if args.command == "build" else check_cli(args)


if __name__ == "__main__":
    main()
