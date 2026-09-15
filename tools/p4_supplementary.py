# P4.1 - Supplementary results: numbers that the research log reports but no committed result file holds.
#
# During P2 and P3 a few checks were run as one-off scripts, and only their printed output went into the log. The report may only
# use numbers from committed files, so this script re-runs exactly those checks with the seeds recorded at the time and saves them.
# Each value is written next to the value the log states, so any difference is visible. Nothing here is tuned or new.
#
#   1. P2.0  gate rejection of true pairs          (seed 5, 4000 scenes, T = 4)          log: 378 of 38,683 = 0.98%
#   2. P2.3  greedy without clutter                (seed 9, 100 scenes, T = 4)           log: 100/100 all-singleton partitions; tuple cost medians 12.54 / 19.60 / 28.11
#   3. P2.4  benchmark rebuild reproducibility     (full rebuild into a temporary folder) log: identical, SHA-256 5d494e42962420dc...
#   4. P2.6  Hamming weight of hardware strings    (deterministic, from the committed counts) log: all 10 below the simulator, mean -0.11; corr(CZ, shift) 0.05
#   5. P3.2  random-sampling details               (seed 7, 1000 samples of 4096 shots)  log: best of all 0.995; optimum sampled 0.855; 5.2% of strings >= 0.641
#
# Usage:
#     python tools/p4_supplementary.py              # all checks (the rebuild takes about 2 minutes)
#     python tools/p4_supplementary.py --skip-rebuild

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import gzip
import hashlib
import itertools
import json
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p2_scene import Params, build_tuples, generate, pair_d2  # noqa: E402


def gate_rejection() -> dict:
    params, rng = Params(), np.random.default_rng(5)
    rejected = total = 0
    for _ in range(4000):
        scene = generate(4, params, rng)
        for a, b in itertools.combinations(range(3), 2):
            for i, oi in enumerate(scene.origin[a]):
                for j, oj in enumerate(scene.origin[b]):
                    if oi >= 0 and oi == oj:
                        total += 1
                        rejected += pair_d2(scene.measurements[a][i], scene.covariances[a][i],
                                            scene.measurements[b][j], scene.covariances[b][j]) > params.gate
    return {"true_pairs": total, "rejected": rejected, "rate": rejected / total,
            "logged": {"true_pairs": 38683, "rejected": 378}}


def greedy_without_clutter() -> dict:
    from p2_heuristics import greedy
    from p2_ilp import solve_ilp
    from p2_qubo import members

    out = {}
    for clutter in (0.0, 1.0):
        params, rng = dataclasses.replace(Params(), clutter_per_sensor=clutter), np.random.default_rng(9)
        all_single = optimal = 0
        sizes = {1: [], 2: [], 3: []}
        for _ in range(100):
            scene = generate(4, params, rng)
            ts = build_tuples(scene, params)
            for t, c in zip(ts.tuples, ts.costs):
                sizes[len(members(t))].append(float(c))
            g = greedy(scene, ts)
            all_single += all(len(members(t)) == 1 for t in g["partition"])
            optimal += abs(g["cost"] - solve_ilp(scene, ts)["cost"]) < 1e-6
        out[str(clutter)] = {"scenes": 100, "all_singleton_partitions": all_single, "greedy_optimal": optimal,
                             "tuple_cost_median_by_size": {str(k): float(np.median(v)) for k, v in sizes.items() if v}}
    out["logged"] = {"0.0": {"all_singleton_partitions": 100, "greedy_optimal": 0, "medians": [12.54, 19.60, 28.11]},
                     "1.0": {"all_singleton_partitions": 0, "greedy_optimal": 24}}
    return out


def benchmark_rebuild() -> dict:
    committed = ROOT / "benchmark" / "p2"
    digest = lambda path: hashlib.sha256(gzip.open(path, "rb").read()).hexdigest()  # noqa: E731

    def rows(path):
        with open(path, encoding="utf-8") as f:
            return [{k: v for k, v in r.items() if not k.endswith("_seconds")} for r in csv.DictReader(f)]

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, str(ROOT / "src" / "p2_benchmark.py"), "build", "--out", tmp],
                       check=True, capture_output=True)
        return {"committed_sha256": digest(committed / "instances.jsonl.gz"),
                "rebuilt_sha256": digest(pathlib.Path(tmp) / "instances.jsonl.gz"),
                "instances_identical": digest(committed / "instances.jsonl.gz") == digest(pathlib.Path(tmp) / "instances.jsonl.gz"),
                "baselines_identical_ignoring_seconds": rows(committed / "baselines.csv") == rows(pathlib.Path(tmp) / "baselines.csv"),
                "logged": {"sha256_prefix": "5d494e42962420dc"}}


def hamming_shift() -> dict:
    from p1_5_hardware import counts_to_probs
    from p1_qaoa import simulate
    from p2_6_hardware import P2_5_FILE, rebuild_sparse
    from p2_qaoa import enumerate_strings, prepare

    record = json.loads((ROOT / "results" / "p2_6-hardware-20260914-163413.json").read_text(encoding="utf-8"))
    sparse = rebuild_sparse(json.loads(P2_5_FILE.read_text(encoding="utf-8")))
    rows = []
    for it in record["experiments"]["B"]["items"]:
        scene, ts = sparse[it["index"]]
        strings = enumerate_strings(scene, ts)
        prep = prepare(scene, ts, it["A"], strings)
        weight = strings["X"].sum(axis=1)
        sim = float(simulate(prep["diag"], it["qubits"], it["gammas"], it["betas"]) @ weight)
        hw = float(counts_to_probs(it["counts"], it["qubits"]) @ weight)
        rows.append({"index": it["index"], "cz": it["two_qubit_gates"], "sim_mean_weight": sim, "hardware_mean_weight": hw,
                     "shift": hw - sim, "retention": it["hardware_corrected"]["p_optimal"] / it["simulator"]["p_optimal"]})
    shift = np.array([r["shift"] for r in rows])
    cz = np.array([r["cz"] for r in rows])
    ret = np.array([r["retention"] for r in rows])
    rank = lambda v: np.argsort(np.argsort(v))  # noqa: E731
    return {"instances": rows, "mean_shift": float(shift.mean()), "negative_shifts": int((shift < 0).sum()),
            "corr_cz_shift": float(np.corrcoef(cz, shift)[0, 1]), "corr_shift_retention": float(np.corrcoef(shift, ret)[0, 1]),
            "spearman_cz_retention": float(np.corrcoef(rank(cz), rank(ret))[0, 1]),
            "logged": {"mean_shift": -0.11, "negative_shifts": 10, "corr_cz_shift": 0.05, "corr_shift_retention": 0.32,
                       "spearman_cz_retention": 0.52}}


def random_sampling_details() -> dict:
    from p3_qantis_qaoa import SHOTS, make_problem, top10_quality

    pr = make_problem()
    rng = np.random.default_rng(7)
    n = 1 << pr["n"]
    uniform = np.full(n, 1 / n)
    best, top_rev, found = [], [], []
    for _ in range(1000):
        c = rng.multinomial(SHOTS, uniform)
        best.append(float(pr["E"][c > 0].min() / pr["E_opt"]))
        top_rev.append(top10_quality(c, pr["E"][pr["rev"]], pr["E_opt"], rng))
        found.append(bool(c[pr["argmin"]] > 0))
    return {"samples": 1000, "shots": SHOTS, "best_of_all_mean": float(np.mean(best)),
            "optimum_sampled_share": float(np.mean(found)), "optimum_sampled_theory": float(1 - (1 - 1 / n) ** SHOTS),
            "top10_reversed_mean": float(np.mean(top_rev)),
            "share_of_strings_at_or_above_0.641": float(np.mean(pr["E"] / pr["E_opt"] >= 0.641)),
            "lowest_levels_over_optimum": [float(v) for v in np.sort(pr["E"])[:10] / pr["E_opt"]],
            "logged": {"best_of_all_mean": 0.995, "optimum_sampled_share": 0.855, "share_of_strings_at_or_above_0.641": 0.052}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-rebuild", action="store_true")
    args = parser.parse_args()
    record = {"timestamp": dt.datetime.now().astimezone().isoformat(),
              "experiment": "P4.1 supplementary results for numbers previously only in the research log",
              "p2_0_gate_rejection": gate_rejection(),
              "p2_3_greedy_without_clutter": greedy_without_clutter(),
              "p2_6_hamming_shift": hamming_shift(),
              "p3_2_random_sampling": random_sampling_details()}
    if not args.skip_rebuild:
        record["p2_4_benchmark_rebuild"] = benchmark_rebuild()
    for key, value in record.items():
        if isinstance(value, dict):
            print(key, {k: v for k, v in value.items() if k not in ("instances",)})
    out = ROOT / "results" / ("p4_supplementary-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
