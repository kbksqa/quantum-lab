# P2.1 - Exact optimum of the multi-sensor association problem by integer linear programming, and the brute-force gate.
#
#   variables   x_k in {0, 1}, one per kept tuple k (from p2_scene.build_tuples)
#   minimise    sum_k c_k x_k
#   subject to  for every real measurement (s, j):  sum of x_k over the tuples that contain it = 1
#
# Solved with scipy.optimize.milp (HiGHS), relative MIP gap set to 0 so "optimal" means optimal.
#
# Independent check ("brute force"): enumerate every valid partition by exact-cover search - no costs are used to prune,
# so it cannot share a mistake with the solver - and take the cheapest.
#
# Usage:
#     python src/p2_ilp.py                        # H1 gate on tiny scenes + H4 (optimum vs truth) + ILP sizes and times
#     python src/p2_ilp.py --gate-scenes 100 --h4-scenes 1000

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from p2_scene import PURE, RESULTS, Params, build_tuples, generate, is_partition, partition_cost, truth_partition

TIE = 1e-9


def measurement_index(scene) -> dict:
    index = {}
    for s, m in enumerate(scene.measurements):
        for j in range(len(m)):
            index[s, j + 1] = len(index)
    return index


def solve_ilp(scene, tuple_set) -> dict:
    index = measurement_index(scene)
    K = len(tuple_set.tuples)
    if not index:
        return {"status": "empty", "partition": [], "cost": 0.0, "seconds": 0.0}
    rows, cols = [], []
    for k, tup in enumerate(tuple_set.tuples):
        for s, i in enumerate(tup):
            if i > 0:
                rows.append(index[s, i])
                cols.append(k)
    A = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(index), K)).tocsr()
    start = time.perf_counter()
    result = milp(c=tuple_set.costs, constraints=LinearConstraint(A, 1, 1), integrality=np.ones(K),
                  bounds=Bounds(0, 1), options={"mip_rel_gap": 0})
    seconds = time.perf_counter() - start
    if result.status != 0:
        return {"status": "solver status %d: %s" % (result.status, result.message), "partition": None,
                "cost": math.inf, "seconds": seconds}
    chosen = [tuple_set.tuples[k] for k in range(K) if result.x[k] > 0.5]
    return {"status": "optimal", "partition": sorted(chosen), "cost": float(result.fun), "seconds": seconds,
            "max_integrality_error": float(np.max(np.minimum(result.x, 1 - result.x)))}


def enumerate_partitions(scene, tuple_set, limit: int) -> dict | None:
    """Exact-cover search over all valid partitions. Returns None when there are more than `limit`."""
    order = list(measurement_index(scene))
    members = [[(s, i) for s, i in enumerate(tup) if i > 0] for tup in tuple_set.tuples]
    containing = {m: [] for m in order}
    for k, ms in enumerate(members):
        for m in ms:
            containing[m].append(k)

    state = {"count": 0, "best": math.inf, "second": math.inf, "best_partition": None}
    covered = set()
    chosen = []

    def search(position: int) -> bool:
        while position < len(order) and order[position] in covered:
            position += 1
        if position == len(order):
            state["count"] += 1
            if state["count"] > limit:
                return False
            cost = float(sum(tuple_set.costs[k] for k in chosen))
            if cost < state["best"]:
                state["second"], state["best"] = state["best"], cost
                state["best_partition"] = sorted(tuple_set.tuples[k] for k in chosen)
            elif cost < state["second"]:
                state["second"] = cost
            return True
        for k in containing[order[position]]:
            if any(m in covered for m in members[k]):
                continue
            covered.update(members[k])
            chosen.append(k)
            ok = search(position + 1)
            chosen.pop()
            covered.difference_update(members[k])
            if not ok:
                return False
        return True

    if not search(0):
        return None
    if not order:
        state.update(count=1, best=0.0, best_partition=[])
    return {"partitions": state["count"], "cost": state["best"], "second": state["second"],
            "partition": state["best_partition"]}


def wilson(successes: int, n: int, z: float = 1.96) -> list:
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [centre - half, centre + half]


def gate_study(params: Params, sizes: tuple, scenes: int, limit: int, rng, label: str) -> dict:
    out = {"mode": label, "sizes": {}}
    for T in sizes:
        row = {"checked": 0, "skipped_over_limit": 0, "mismatch": 0, "max_abs_difference": 0.0,
               "same_partition": 0, "near_ties": 0, "invalid_ilp_partition": 0, "solver_not_optimal": 0,
               "partitions_max": 0}
        for _ in range(scenes):
            scene = generate(T, params, rng)
            ts = build_tuples(scene, params)
            ilp = solve_ilp(scene, ts)
            if ilp["status"] not in ("optimal", "empty"):
                row["solver_not_optimal"] += 1
                continue
            if not is_partition(scene, ilp["partition"]) or abs(partition_cost(ts, ilp["partition"]) - ilp["cost"]) > 1e-6:
                row["invalid_ilp_partition"] += 1
            brute = enumerate_partitions(scene, ts, limit)
            if brute is None:
                row["skipped_over_limit"] += 1
                continue
            row["checked"] += 1
            row["partitions_max"] = max(row["partitions_max"], brute["partitions"])
            difference = abs(ilp["cost"] - brute["cost"])
            row["max_abs_difference"] = max(row["max_abs_difference"], difference)
            row["mismatch"] += difference > 1e-6
            row["same_partition"] += ilp["partition"] == brute["partition"]
            row["near_ties"] += brute["second"] - brute["cost"] < TIE
        out["sizes"][str(T)] = row
    return out


MODES = ("clutter joined to a target tuple", "measurements of different targets joined",
         "target measurement left as a singleton", "truth cut by gate")


def difference_modes(scene, found: list, truth: list, truth_cost: float) -> set:
    """How a found partition differs from the truth. A scene can show several modes at once."""
    def groups(partition):
        size, members = {}, []
        for tup in partition:
            ms = [(s, i) for s, i in enumerate(tup) if i > 0]
            members.append(ms)
            for m in ms:
                size[m] = len(ms)
        return size, members

    source = lambda m: scene.origin[m[0]][m[1] - 1]  # noqa: E731
    modes = set()
    found_size, found_members = groups(found)
    truth_size, _ = groups(truth)
    for ms in found_members:
        sources = [source(m) for m in ms]
        if len(ms) >= 2 and -1 in sources:
            modes.add(MODES[0])
        if len({x for x in sources if x >= 0}) >= 2:
            modes.add(MODES[1])
    if any(source(m) >= 0 and truth_size[m] >= 2 and found_size[m] == 1 for m in truth_size):
        modes.add(MODES[2])
    if math.isinf(truth_cost):
        modes.add(MODES[3])
    return modes


VARIANTS = (
    ("default", {}),
    ("no clutter", {"clutter_per_sensor": 0.0}),
    ("P_D = 1", {"p_detect": 1.0}),
    ("pure (P_D = 1, no clutter, no gate)", dict(PURE)),
    ("bearing 0.005 rad (about 10 m round)", {"sigma_bearing": 0.005}),
    ("spacing 100 m", {"spacing": 100.0}),
    ("spacing 200 m", {"spacing": 200.0}),
    ("bearing 0.005 rad and no clutter", {"sigma_bearing": 0.005, "clutter_per_sensor": 0.0}),
)


def factor_study(base: Params, T: int, scenes: int, seed: int) -> list:
    """Diagnosis, added after H4 failed: change one factor at a time, same scene seed for every variant."""
    rows = []
    for name, change in VARIANTS:
        params = dataclasses.replace(base, **change)
        rng = np.random.default_rng(seed)
        hits = 0
        for _ in range(scenes):
            scene = generate(T, params, rng)
            hits += solve_ilp(scene, build_tuples(scene, params))["partition"] == truth_partition(scene)
        rows.append({"variant": name, "change": change, "share_optimum_equals_truth": hits / scenes,
                     "wilson95": wilson(hits, scenes)})
    return rows


def truth_study(params: Params, T: int, scenes: int, rng) -> dict:
    optimum_is_truth = truth_cut = model_prefers_other = cheaper_than_optimum = 0
    seconds, variables, partition_diff = [], [], []
    modes = {mode: 0 for mode in MODES}
    for _ in range(scenes):
        scene = generate(T, params, rng)
        ts = build_tuples(scene, params)
        ilp = solve_ilp(scene, ts)
        truth = truth_partition(scene)
        truth_cost = partition_cost(ts, truth)
        seconds.append(ilp["seconds"])
        variables.append(len(ts.tuples))
        if ilp["partition"] != truth:
            for mode in difference_modes(scene, ilp["partition"], truth, truth_cost):
                modes[mode] += 1
        if ilp["partition"] == truth:
            optimum_is_truth += 1
        elif math.isinf(truth_cost):
            truth_cut += 1
        else:
            model_prefers_other += 1
            partition_diff.append(truth_cost - ilp["cost"])
            cheaper_than_optimum += truth_cost < ilp["cost"] - 1e-6
    return {
        "targets": T,
        "scenes": scenes,
        "share_optimum_equals_truth": optimum_is_truth / scenes,
        "wilson95": wilson(optimum_is_truth, scenes),
        "truth_cut_by_gate": truth_cut,
        "truth_feasible_but_costlier": model_prefers_other,
        "truth_cheaper_than_ilp_optimum": cheaper_than_optimum,
        "difference_modes_scenes": modes,
        "median_cost_excess_of_truth": float(np.median(partition_diff)) if partition_diff else None,
        "variables_mean": float(np.mean(variables)),
        "variables_max": int(max(variables)),
        "ilp_seconds_median": float(np.median(seconds)),
        "ilp_seconds_max": float(max(seconds)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate-scenes", type=int, default=200)
    parser.add_argument("--h4-scenes", type=int, default=500)
    parser.add_argument("--factor-scenes", type=int, default=300)
    parser.add_argument("--limit", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=2027)
    args = parser.parse_args()

    params = Params()
    pure = dataclasses.replace(params, **PURE)
    rng = np.random.default_rng(args.seed)
    record = {"timestamp": dt.datetime.now().astimezone().isoformat(), "experiment": "P2.1 exact ILP and brute-force gate",
              "seed": args.seed, "params": dataclasses.asdict(params), "brute_force_limit": args.limit}

    print("H1 gate: ILP optimum vs exact-cover enumeration of every partition")
    record["gate"] = [gate_study(params, (1, 2, 3, 4), args.gate_scenes, args.limit, rng, "augmented"),
                      gate_study(pure, (2, 3), args.gate_scenes // 4, args.limit, rng, "pure")]
    for study in record["gate"]:
        for T, r in study["sizes"].items():
            print("  %-9s T=%s  checked %3d  skipped %3d  mismatch %d  max|diff| %.2e  same partition %3d  near ties %d"
                  "  invalid %d  not optimal %d  partitions max %d"
                  % (study["mode"], T, r["checked"], r["skipped_over_limit"], r["mismatch"], r["max_abs_difference"],
                     r["same_partition"], r["near_ties"], r["invalid_ilp_partition"], r["solver_not_optimal"],
                     r["partitions_max"]))

    print("H4: exact optimum equals the truth (partition), default parameters")
    record["truth"] = {}
    for T, n in ((3, args.h4_scenes), (2, 200), (4, 200), (5, 200), (6, 200)):
        s = truth_study(params, T, n, rng)
        record["truth"][str(T)] = s
        print("  T=%d  scenes %d  optimum = truth %.3f  [%.3f, %.3f]  truth cut %d  truth feasible but costlier %d"
              "  (truth cheaper than ILP: %d)  vars mean %.1f max %d  ILP s median %.4f max %.4f"
              % (T, n, s["share_optimum_equals_truth"], *s["wilson95"], s["truth_cut_by_gate"],
                 s["truth_feasible_but_costlier"], s["truth_cheaper_than_ilp_optimum"], s["variables_mean"],
                 s["variables_max"], s["ilp_seconds_median"], s["ilp_seconds_max"]))
        print("       scenes showing each difference: %s" % s["difference_modes_scenes"])

    print("Diagnosis (added after H4 failed): one factor at a time, T=3, same scene seed per variant")
    record["factor_study"] = factor_study(params, 3, args.factor_scenes, args.seed + 1)
    for row in record["factor_study"]:
        print("  %-38s optimum = truth %.3f  [%.3f, %.3f]" % (row["variant"], row["share_optimum_equals_truth"], *row["wilson95"]))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p2_1-ilp-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
