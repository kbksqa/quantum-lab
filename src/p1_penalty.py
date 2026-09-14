# P1.2 - How large must the QUBO penalty be, and what does a large penalty cost?
#
# Energy of any bit string x:  E_A(x) = cost(x) + A * V(x)
#   cost(x) = sum of c over selected cells,  V(x) = sum_rows (sum x - 1)^2 + sum_cols (sum x - 1)^2
#
# 1. Exact critical penalty. Feasible strings have V = 0, so the optimum wins iff for every infeasible x
#        optimum < cost(x) + A * V(x)   <=>   A > (optimum - cost(x)) / V(x)
#    so  A_crit = max(0, max over infeasible x of (optimum - cost(x)) / V(x)),  computed by enumeration.
#
# 2. Landscape. For A = s * A_crit: the normalised gap (E1 - E0) / (Emax - E0) between the ground level
#    and the next distinct energy level, relative to the whole energy range.
#
# 3. Search cost. Single-bit-flip simulated annealing with the same budget for every A.
#    Schedule (stated because the result depends on it): geometric from T_start = largest single-flip
#    |dE| (grows with A) down to T_end = 0.05 * (max c - min c) (independent of A).
#
# Usage:
#     python src/p1_penalty.py
#     python src/p1_penalty.py --instances 50 --restarts 64 --sweeps 100

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json

import numpy as np

from p1_qubo import build_qubo, hungarian_cost, prune_augmented, safe_penalty
from p1_scenario import RESULTS, Params, augmented_cost, generate, pure_cost

MULTIPLIERS = [1.1, 1.5, 2.0, 5.0, 10.0, 50.0]


def enumerate_strings(C: np.ndarray) -> dict:
    n = C.shape[0]
    variables = [(i, j) for i in range(n) for j in range(n) if np.isfinite(C[i, j])]
    m = len(variables)
    costs = np.array([C[i, j] for i, j in variables])
    idx = np.arange(1 << m, dtype=np.int64)
    X = ((idx[:, None] >> np.arange(m)) & 1).astype(np.int16)
    row_of = np.zeros((n, m), dtype=np.int16)
    col_of = np.zeros((n, m), dtype=np.int16)
    for k, (i, j) in enumerate(variables):
        row_of[i, k] = 1
        col_of[j, k] = 1
    rows = (X @ row_of.T).astype(np.int32)
    cols = (X @ col_of.T).astype(np.int32)
    return {
        "variables": variables,
        "costs": costs,
        "X": X,
        "cost": X.astype(float) @ costs,
        "V": ((rows - 1) ** 2).sum(axis=1) + ((cols - 1) ** 2).sum(axis=1),
    }


def critical_penalty(strings: dict, optimum: float) -> float:
    infeasible = strings["V"] > 0
    ratios = (optimum - strings["cost"][infeasible]) / strings["V"][infeasible]
    return max(0.0, float(ratios.max()))


def landscape(strings: dict, A: float, tol: float = 1e-9) -> dict:
    E = strings["cost"] + A * strings["V"]
    e0 = float(E.min())
    above = E[E > e0 + tol * max(1.0, abs(e0))]
    e1 = float(above.min()) if above.size else e0
    e_max = float(E.max())
    return {
        "E0": e0,
        "E1": e1,
        "Emax": e_max,
        "normalised_gap": (e1 - e0) / (e_max - e0) if e_max > e0 else 0.0,
        "ground_degeneracy": int(np.sum(E <= e0 + tol * max(1.0, abs(e0)))),
    }


def anneal(qubo: dict, restarts: int, sweeps: int, rng: np.random.Generator) -> np.ndarray:
    Q = qubo["Q"]
    m = Q.shape[0]
    J = Q + Q.T
    diag = np.diag(Q).copy()
    np.fill_diagonal(J, 0.0)
    t_start = float(np.max(np.abs(diag) + np.abs(J).sum(axis=1)))
    spread = float(qubo["costs"].max() - qubo["costs"].min())
    t_end = max(0.05 * spread, 1e-6)
    temperatures = np.geomspace(max(t_start, t_end * 1.0001), t_end, sweeps)

    x = rng.integers(0, 2, size=(restarts, m)).astype(float)
    for T in temperatures:
        for k in range(m):
            dE = (1.0 - 2.0 * x[:, k]) * (diag[k] + x @ J[:, k])
            accept = (dE <= 0) | (rng.random(restarts) < np.exp(-np.clip(dE, 0, None) / T))
            x[accept, k] = 1.0 - x[accept, k]
    return x.astype(int)


def score_states(states: np.ndarray, qubo: dict, optimum: float) -> dict:
    n = qubo["n"]
    rows = np.zeros((states.shape[0], n), dtype=int)
    cols = np.zeros((states.shape[0], n), dtype=int)
    for k, (i, j) in enumerate(qubo["variables"]):
        rows[:, i] += states[:, k]
        cols[:, j] += states[:, k]
    feasible = np.all(rows == 1, axis=1) & np.all(cols == 1, axis=1)
    cost = states @ qubo["costs"]
    optimal = feasible & (np.abs(cost - optimum) <= 1e-6 * max(1.0, abs(optimum)))
    return {"feasible_share": float(feasible.mean()), "success": float(optimal.mean())}


def study_instance(C: np.ndarray, restarts: int, sweeps: int, rng: np.random.Generator) -> dict:
    optimum = hungarian_cost(C)
    strings = enumerate_strings(C)
    a_crit = critical_penalty(strings, optimum)
    base = a_crit if a_crit > 0 else 1e-6
    a_safe = safe_penalty(strings["costs"])
    max_abs = float(np.abs(strings["costs"]).max())
    rows = []
    for label, A in [("x%g" % s, s * base) for s in MULTIPLIERS] + [("safe", a_safe)]:
        land = landscape(strings, A)
        qubo = build_qubo(C, penalty=A)
        sa = score_states(anneal(qubo, restarts, sweeps, rng), qubo, optimum)
        rows.append({"label": label, "A": A, "A_over_Acrit": A / base,
                     "normalised_gap": land["normalised_gap"], "ground_degeneracy": land["ground_degeneracy"],
                     "sa_success": sa["success"], "sa_feasible_share": sa["feasible_share"]})
    return {"variables": len(strings["variables"]), "optimum": optimum, "A_crit": a_crit, "A_safe": a_safe,
            "safe_over_crit": a_safe / base, "max_abs_cost": max_abs,
            "max_abs_cost_is_enough": bool(max_abs > a_crit), "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", type=int, default=50)
    parser.add_argument("--restarts", type=int, default=64)
    parser.add_argument("--sweeps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--max-vars", type=int, default=18)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    base = Params()
    pure = dataclasses.replace(base, p_detect=1.0, clutter_per_scan=0.0, gate=None)

    settings = {"pure 3x3": [], "pure 4x4": [], "augmented 2 targets": []}
    while min(len(v) for v in settings.values()) < args.instances:
        if len(settings["pure 3x3"]) < args.instances:
            settings["pure 3x3"].append(pure_cost(generate(3, pure, rng)))
        if len(settings["pure 4x4"]) < args.instances:
            settings["pure 4x4"].append(pure_cost(generate(4, pure, rng)))
        if len(settings["augmented 2 targets"]) < args.instances:
            scene = generate(2, base, rng)
            C, info = augmented_cost(scene, base)
            P = prune_augmented(C, info["tracks"], info["measurements"])
            if int(np.isfinite(P).sum()) <= args.max_vars:
                settings["augmented 2 targets"].append(P)

    summary = {}
    for name, matrices in settings.items():
        studies = [study_instance(C, args.restarts, args.sweeps, rng) for C in matrices]
        labels = [r["label"] for r in studies[0]["rows"]]
        per_label = {}
        for idx, label in enumerate(labels):
            per_label[label] = {
                "median_normalised_gap": float(np.median([s["rows"][idx]["normalised_gap"] for s in studies])),
                "mean_sa_success": float(np.mean([s["rows"][idx]["sa_success"] for s in studies])),
                "mean_sa_feasible_share": float(np.mean([s["rows"][idx]["sa_feasible_share"] for s in studies])),
                "median_A_over_Acrit": float(np.median([s["rows"][idx]["A_over_Acrit"] for s in studies])),
            }
        summary[name] = {
            "instances": len(studies),
            "variables_mean": float(np.mean([s["variables"] for s in studies])),
            "median_safe_over_crit": float(np.median([s["safe_over_crit"] for s in studies])),
            "share_max_abs_cost_enough": float(np.mean([s["max_abs_cost_is_enough"] for s in studies])),
            "by_penalty": per_label,
        }
        print("== %s: %d instances, %.1f variables ==" % (name, len(studies), summary[name]["variables_mean"]))
        print("   safe A is a median %.1fx the critical A;  A = max|c| is enough in %.0f%% of instances"
              % (summary[name]["median_safe_over_crit"], 100 * summary[name]["share_max_abs_cost_enough"]))
        print("   A/A_crit    norm.gap    SA success   SA feasible")
        for label in labels:
            row = per_label[label]
            print("   %8.1f    %8.4f    %9.3f    %9.3f"
                  % (row["median_A_over_Acrit"], row["median_normalised_gap"], row["mean_sa_success"],
                     row["mean_sa_feasible_share"]))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p1_2-penalty-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    out.write_text(json.dumps({
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P1.2 penalty study",
        "seed": args.seed,
        "instances_per_setting": args.instances,
        "annealing": {"restarts": args.restarts, "sweeps": args.sweeps,
                      "schedule": "geometric, T_start = max single-flip |dE|, T_end = 0.05 * cost spread"},
        "multipliers_of_A_crit": MULTIPLIERS,
        "summary": summary,
    }, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
