# P3.3 - Question Q4: the 19-variable QANTIS instance (N = 3 tracks, M = 4 measurements) on the noiseless simulator.
#
# The paper reports this instance only on hardware (ibm_marrakesh): quality 20.4% at p = 1 and 11.5% at p = 2, with the
# optimum stated as -132.0 (Table 15 footnote). Q4 asks what the same method gives without noise, and - after P3.2 - what
# uniformly random bitstrings give on the same metric.
#
# Instance: the P3.1 generator with N = 3, M = 4 (same seed 42, same "code" cost variant), 19 variables, 2^19 states.
# Method: A, the paper's FPC-QAOA (P3.2), at p = 1 and 2. Metrics as in P3.2, with 100 samples of 4096 shots per distribution;
# the random baseline uses 200 samples.
#
# Usage:
#     python src/p3_qantis_q4.py
#     python src/p3_qantis_q4.py --qantis-repo <clone of neuraparse/qantis>     # adds the cross-check of Q and the Hungarian value

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import time

import numpy as np

from p3_qantis_instance import RESULTS, cross_check, gnn_as_coded, hungarian_as_coded
from p3_qantis_qaoa import SHOTS, make_problem, method_a, metrics, probabilities, top10_quality

N_TRACKS, N_MEAS = 3, 4
PAPER_OPTIMUM = -132.0
PAPER_HARDWARE = {1: 0.204, 2: 0.115}
REPS, RANDOM_REPS = 100, 200


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qantis-repo", type=str, default=None)
    args = parser.parse_args()

    rng = np.random.default_rng(2034)
    start = time.perf_counter()
    pr = make_problem(1.5, N_TRACKS, N_MEAS)
    qubo = pr["qubo"]
    hung = hungarian_as_coded(qubo)
    gnn = gnn_as_coded(qubo)
    record = {
        "timestamp": dt.datetime.now().astimezone().isoformat(), "experiment": "P3.3 Q4: 19-variable QANTIS instance on a simulator",
        "variables": pr["n"], "quadratic_terms": int(np.count_nonzero(np.triu(qubo["Q"], 1))), "penalty": qubo["penalty"],
        "optimum": pr["E_opt"], "optimum_unique": int(pr["optimal"].sum()) == 1, "feasible_strings": int(pr["feasible"].sum()),
        "uniform_p_optimal": float(pr["optimal"].mean()),
        "hungarian_as_coded": {"association": list(hung["association"]), "objective": hung["objective"]},
        "gnn_as_coded": {"association": list(gnn["association"]), "objective_full": gnn["objective_full"],
                         "objective_pairs_only": gnn["objective_pairs_only"]},
        "paper_optimum": PAPER_OPTIMUM, "paper_hardware_quality": PAPER_HARDWARE,
    }
    print("19-variable instance: lambda %.4f, optimum %.4f (unique %s), feasible strings %d, uniform P(opt) %.2e"
          % (qubo["penalty"], pr["E_opt"], record["optimum_unique"], record["feasible_strings"], record["uniform_p_optimal"]))
    print("Hungarian as coded %.4f (paper %.1f, difference %.4f); GNN full %.4f; brute-force optimum is Hungarian: %s"
          % (hung["objective"], PAPER_OPTIMUM, abs(hung["objective"] - PAPER_OPTIMUM), gnn["objective_full"],
             abs(hung["objective"] - pr["E_opt"]) < 1e-9))

    if args.qantis_repo:
        ours = {"Q": qubo["Q"].tolist(), "penalty": qubo["penalty"], "hungarian_as_coded": {"objective": hung["objective"]}}
        cc = cross_check(pathlib.Path(args.qantis_repo), ours, N_TRACKS, N_MEAS)
        record["cross_check"] = cc
        print("cross-check with repository %s: max |Q diff| %.2e, Hungarian %.6f vs %.6f"
              % (cc["repository_commit"][:7], cc["Q_max_abs_difference"], cc["hungarian_theirs"], cc["hungarian_ours"]))

    record["method_a"] = {}
    for p in (1, 2):
        t0 = time.perf_counter()
        out = method_a(pr, p)
        m = metrics(pr, probabilities(pr, out["gammas"], out["betas"]), rng, reps=REPS)
        record["method_a"]["p%d" % p] = {**m, "coefficients": out["coefficients"], "evaluations": out["evaluations"],
                                         "seconds": time.perf_counter() - t0}
        print("A p=%d: P(opt) %.2e  P(feas) %.4f  <E>/opt %.3f  top-10 %.3f (sd %.3f)  reversed %.3f  best-of-all %.3f  "
              "[paper hardware %.3f]  (%.0f s)"
              % (p, m["p_optimal"], m["p_feasible"], m["expectation_over_optimum"], m["quality_top10_mean"], m["quality_top10_sd"],
                 m["quality_top10_reversed_mean"], m["quality_best_of_all_samples_mean"], PAPER_HARDWARE[p],
                 time.perf_counter() - t0))

    uniform = np.full(1 << pr["n"], 1.0 / (1 << pr["n"]))
    qs, best = [], []
    for _ in range(RANDOM_REPS):
        counts = rng.multinomial(SHOTS, uniform)
        qs.append(top10_quality(counts, pr["E"], pr["E_opt"], rng))
        best.append(float(pr["E"][counts > 0].min() / pr["E_opt"]))
    qs = np.array(qs)
    record["random_baseline"] = {"samples": RANDOM_REPS, "mean": float(qs.mean()), "sd": float(qs.std()),
                                 "p5": float(np.percentile(qs, 5)), "p95": float(np.percentile(qs, 95)),
                                 "share_at_or_above_0.204": float(np.mean(qs >= 0.204)),
                                 "best_of_all_mean": float(np.mean(best))}
    rb = record["random_baseline"]
    print("uniform random: top-10 mean %.3f sd %.3f p5 %.3f p95 %.3f, share >= 0.204: %.3f; best-of-all mean %.3f"
          % (rb["mean"], rb["sd"], rb["p5"], rb["p95"], rb["share_at_or_above_0.204"], rb["best_of_all_mean"]))
    record["seconds"] = time.perf_counter() - start

    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / ("p3_3-q4-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    path.write_text(json.dumps(record, indent=2, default=lambda v: v.item() if isinstance(v, np.generic) else str(v)),
                    encoding="utf-8")
    print("saved %s (%.0f s)" % (path, record["seconds"]))


if __name__ == "__main__":
    main()
