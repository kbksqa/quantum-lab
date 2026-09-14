# P3.2 - QANTIS FPC-QAOA on a noiseless simulator (claim C2), the quality-metric baseline (Q1), standard metrics (Q2),
# and the penalty rule (Q3). Instance: the rebuilt 2 x 3 instance of P3.1 (cost variant "code", identical to the authors').
#
# QAOA layer as in Qiskit's QAOAAnsatz: exp(-i gamma H_C), then exp(-i beta sum X), starting from |+>^n. H_C is the
# unscaled Ising form of the QUBO (qiskit_optimization.to_ising does not rescale), so the simulator uses the QUBO energies
# directly as the diagonal phase. p1_qaoa.simulate implements the layer and is checked against Qiskit in the tests.
#
# Methods simulated (see docs/p3-sources.md section 2):
#   A "paper FPC"        : 2k = 6 trainable polynomial coefficients (k = 3), gamma(t) and beta(t) digitised at t = (l + 0.5)/p;
#                          start gamma(t) = pi t, beta(t) = pi/4; COBYLA, 100 iterations, minimising <H>.  C2 is graded on A.
#   B "public code"      : standard QAOA, all 2p angles trained by COBYLA (100 iterations), starting from the interleaved
#                          schedule vector read in QAOAAnsatz parameter order (all beta, then all gamma).
#   C "initial, correct" : the analytical schedule gamma(t) = pi t, beta(t) = pi/4, no training.
#   D "initial, as bound": the same schedule bound the way the public hardware script binds it (misordered).
#
# Metrics for each output distribution:
#   - the paper's quality: sample 4096 shots, take the 10 most frequent bitstrings (ties broken at random), best energy / optimum;
#     repeated 200 times; evaluated with the correct bit order and with the reversed order of the public script
#   - best energy among all 4096 samples / optimum (what a solver returning its best sample reports)
#   - P(optimal), P(feasible), <E> / optimum
#
# C2 (registered): method A at p = 3 reaches mean quality >= 0.641 - 0.033 = 0.608 (correct bit order).
# Q1 (registered): the paper's quality for uniformly random bitstrings, 1,000 samples of 4096 shots; the headline 0.641 is
#                  "informative" only if it exceeds the 95th percentile.
#
# Usage:
#     python src/p3_qantis_qaoa.py

from __future__ import annotations

import datetime as dt
import json
import math

import numpy as np
from scipy.optimize import minimize

from p1_qaoa import simulate
from p3_qantis_instance import RESULTS, all_strings, build_qubo, cost_matrix, energy, generate, violation

HEADLINE, HEADLINE_SD = 0.641, 0.033
PAPER_SIM_QUALITY = {1: 0.513, 2: 1.00, 3: 0.909, 4: 0.889}
DEPTHS = [1, 2, 3, 4]
K, MAXITER, SHOTS, REPS, RANDOM_REPS = 3, 100, 4096, 200, 1000
GAMMA0 = [0.0, math.pi, 0.0]
BETA0 = [math.pi / 4, 0.0, 0.0]


def schedule(coeffs, p: int) -> np.ndarray:
    t = (np.arange(p) + 0.5) / p
    return np.array([sum(c * tt ** k for k, c in enumerate(coeffs)) for tt in t])


def interleaved_initial(p: int) -> np.ndarray:
    v = np.empty(2 * p)
    v[0::2], v[1::2] = schedule(GAMMA0, p), schedule(BETA0, p)
    return v


def bind_like_script(v: np.ndarray, p: int) -> tuple[np.ndarray, np.ndarray]:
    """dict(zip(QAOAAnsatz.parameters, v)): the parameters are beta[0..p-1] then gamma[0..p-1]. Returns (gammas, betas)."""
    return np.asarray(v[p:]), np.asarray(v[:p])


def make_problem(multiplier: float = 1.5, n_tracks: int = 2, n_meas: int = 3) -> dict:
    scene = generate(n_tracks, n_meas)
    C, mask, _ = cost_matrix(scene, "code")
    qubo = build_qubo(C, mask, multiplier=multiplier)
    n = qubo["Q"].shape[0]
    X = all_strings(n)
    E = energy(qubo, X)
    V = violation(qubo, X)
    e_opt = float(E.min())
    rev = np.array([int(format(k, "0%db" % n)[::-1], 2) for k in range(1 << n)])
    return {"qubo": qubo, "n": n, "E": E, "feasible": V == 0, "optimal": np.isclose(E, e_opt, atol=1e-9),
            "E_opt": e_opt, "rev": rev, "argmin": int(np.argmin(E))}


def probabilities(pr: dict, gammas, betas) -> np.ndarray:
    return simulate(pr["E"], pr["n"], gammas, betas)


def expectation(pr: dict, gammas, betas) -> float:
    return float(probabilities(pr, gammas, betas) @ pr["E"])


def method_a(pr: dict, p: int) -> dict:
    res = minimize(lambda v: expectation(pr, schedule(v[:K], p), schedule(v[K:], p)), np.array(GAMMA0 + BETA0),
                   method="COBYLA", options={"maxiter": MAXITER})
    return {"gammas": schedule(res.x[:K], p), "betas": schedule(res.x[K:], p), "coefficients": res.x.tolist(),
            "evaluations": int(res.nfev)}


def method_b(pr: dict, p: int) -> dict:
    def angles(v):
        return bind_like_script(v, p)

    res = minimize(lambda v: expectation(pr, *angles(v)), interleaved_initial(p), method="COBYLA", options={"maxiter": MAXITER})
    gammas, betas = angles(res.x)
    return {"gammas": gammas, "betas": betas, "evaluations": int(res.nfev)}


def method_c(pr: dict, p: int) -> dict:
    return {"gammas": schedule(GAMMA0, p), "betas": schedule(BETA0, p)}


def method_d(pr: dict, p: int) -> dict:
    gammas, betas = bind_like_script(interleaved_initial(p), p)
    return {"gammas": gammas, "betas": betas}


def top10_quality(counts: np.ndarray, energies: np.ndarray, e_opt: float, rng) -> float:
    order = np.lexsort((rng.random(len(counts)), -counts))
    top = order[:10]
    top = top[counts[top] > 0]
    return float(energies[top].min() / e_opt)


def metrics(pr: dict, probs: np.ndarray, rng, reps: int = REPS) -> dict:
    probs = np.clip(probs, 0, None)
    probs = probs / probs.sum()
    E, e_opt, E_rev = pr["E"], pr["E_opt"], pr["E"][pr["rev"]]
    q, q_rev, best_all = [], [], []
    for _ in range(reps):
        counts = rng.multinomial(SHOTS, probs)
        q.append(top10_quality(counts, E, e_opt, rng))
        q_rev.append(top10_quality(counts, E_rev, e_opt, rng))
        best_all.append(float(E[counts > 0].min() / e_opt))
    exact_top = np.argsort(-probs, kind="stable")[:10]
    return {
        "p_optimal": float(probs[pr["optimal"]].sum()),
        "p_feasible": float(probs[pr["feasible"]].sum()),
        "expectation_over_optimum": float(probs @ E / e_opt),
        "quality_top10_mean": float(np.mean(q)), "quality_top10_sd": float(np.std(q)),
        "quality_top10_reversed_mean": float(np.mean(q_rev)), "quality_top10_reversed_sd": float(np.std(q_rev)),
        "quality_best_of_all_samples_mean": float(np.mean(best_all)),
        "quality_top10_exact_distribution": float(E[exact_top].min() / e_opt),
        "most_probable_state_is_optimal": bool(pr["optimal"][int(np.argmax(probs))]),
    }


def random_baseline(pr: dict, rng) -> dict:
    uniform = np.full(1 << pr["n"], 1.0 / (1 << pr["n"]))
    qs = np.array([top10_quality(rng.multinomial(SHOTS, uniform), pr["E"], pr["E_opt"], rng) for _ in range(RANDOM_REPS)])
    return {"samples": RANDOM_REPS, "shots": SHOTS, "mean": float(qs.mean()), "sd": float(qs.std()),
            "p5": float(np.percentile(qs, 5)), "p50": float(np.percentile(qs, 50)), "p95": float(np.percentile(qs, 95)),
            "max": float(qs.max()), "share_at_or_above_headline": float(np.mean(qs >= HEADLINE)),
            "share_at_or_above_1": float(np.mean(qs >= 1 - 1e-12))}


def main() -> None:
    rng = np.random.default_rng(2033)
    pr = make_problem()
    print("instance: %d variables, optimum %.4f, feasible strings %d, uniform P(opt) %.5f"
          % (pr["n"], pr["E_opt"], int(pr["feasible"].sum()), float(pr["optimal"].mean())))
    record = {"timestamp": dt.datetime.now().astimezone().isoformat(), "experiment": "P3.2 QANTIS QAOA on a noiseless simulator",
              "settings": {"k": K, "maxiter": MAXITER, "shots": SHOTS, "reps": REPS, "random_reps": RANDOM_REPS,
                           "gamma0": GAMMA0, "beta0": BETA0, "digitisation": "t = (l + 0.5) / p", "seed": 2033},
              "optimum": pr["E_opt"], "methods": {}}

    methods = {"A paper FPC": method_a, "B public code": method_b, "C initial, correct": method_c, "D initial, as bound": method_d}
    print("method               p   P(opt)   P(feas)  <E>/opt  top10 q (sd)      top10 reversed    best-of-all  exact top10")
    for name, fn in methods.items():
        record["methods"][name] = {}
        for p in DEPTHS:
            out = fn(pr, p)
            m = metrics(pr, probabilities(pr, out["gammas"], out["betas"]), rng)
            record["methods"][name]["p%d" % p] = {**m, "gammas": np.asarray(out["gammas"]).tolist(),
                                                  "betas": np.asarray(out["betas"]).tolist(),
                                                  **({"coefficients": out["coefficients"]} if "coefficients" in out else {}),
                                                  **({"evaluations": out["evaluations"]} if "evaluations" in out else {})}
            print("%-20s %d  %.4f  %.4f  %7.3f  %.3f (%.3f)    %.3f (%.3f)     %.3f        %.3f"
                  % (name, p, m["p_optimal"], m["p_feasible"], m["expectation_over_optimum"], m["quality_top10_mean"],
                     m["quality_top10_sd"], m["quality_top10_reversed_mean"], m["quality_top10_reversed_sd"],
                     m["quality_best_of_all_samples_mean"], m["quality_top10_exact_distribution"]))

    baseline = random_baseline(pr, rng)
    record["Q1_random_baseline"] = baseline
    informative = HEADLINE > baseline["p95"]
    print("Q1 uniform random, %d x %d shots: mean %.3f sd %.3f  p5 %.3f  p50 %.3f  p95 %.3f  max %.3f  share >= 0.641: %.3f"
          % (RANDOM_REPS, SHOTS, baseline["mean"], baseline["sd"], baseline["p5"], baseline["p50"], baseline["p95"],
             baseline["max"], baseline["share_at_or_above_headline"]))

    q3 = {}
    for multiplier in (1.0, 1.5):
        prm = make_problem(multiplier)
        q3[str(multiplier)] = {"penalty": prm["qubo"]["penalty"], "optimum": prm["E_opt"],
                               "same_optimal_string": prm["argmin"] == pr["argmin"], "by_depth": {}}
        for p in (1, 2, 3):
            out = method_a(prm, p)
            m = metrics(prm, probabilities(prm, out["gammas"], out["betas"]), rng, reps=100)
            q3[str(multiplier)]["by_depth"]["p%d" % p] = {"p_optimal": m["p_optimal"], "p_feasible": m["p_feasible"],
                                                          "quality_top10_mean": m["quality_top10_mean"]}
        print("Q3 lambda = %.1f max|c| (= %.3f, optimum %.3f, same optimum %s): %s" % (
            multiplier, prm["qubo"]["penalty"], prm["E_opt"], q3[str(multiplier)]["same_optimal_string"],
            {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in q3[str(multiplier)]["by_depth"].items()}))
    record["Q3_penalty_rule"] = q3

    a3 = record["methods"]["A paper FPC"]["p3"]["quality_top10_mean"]
    c2 = "reproduced" if a3 >= HEADLINE - HEADLINE_SD else "not reproduced"
    record["grades"] = {"C2": c2, "C2_method_A_p3_quality": a3, "C2_threshold": HEADLINE - HEADLINE_SD,
                        "Q1_headline_informative": informative, "Q1_p95": baseline["p95"]}
    print("C2 %s (method A, p = 3: mean top-10 quality %.3f against threshold %.3f)" % (c2, a3, HEADLINE - HEADLINE_SD))
    print("Q1 headline 0.641 %s the random 95th percentile %.3f -> %s"
          % ("exceeds" if informative else "does not exceed", baseline["p95"], "informative" if informative else "NOT informative"))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p3_2-qaoa-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps(record, indent=2, default=lambda v: v.item() if isinstance(v, np.generic) else str(v)),
                   encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
