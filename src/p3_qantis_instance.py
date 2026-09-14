# P3.1 - Rebuild the QANTIS 2 x 3 data-association instance (arXiv:2603.00785) and test claims C1 and C4.
#
# Re-implemented here from the paper and from the audit of the public repository (docs/p3-sources.md); no code is copied.
#
# Instance (as the public generator does it): default_rng(42); predicted positions N x 2 standard normal, then measurements
# M x 2 standard normal; innovation covariance S = 0.5 I for every track; chi-square gate 9.21.
#
# Costs, two variants:
#   "code"  : c_ij = 1/2 (d^2 + ln det 2 pi S) + ln(clutter density 1e-5)   (what the repository computes)
#   "paper" : c_ij = 1/2 (d^2 + ln det 2 pi S)                             (Eq. in paper Sec 6.1)
#   An ungated pair keeps its variable with cost 0 in both (what the repository does).
#
# Variables: x_ij row by row, then m_i (missed detection) for each track, then f_j (false alarm) for each measurement.
# QUBO (Eq. 7): sum c_ij x_ij + c_miss sum m_i + c_fa sum f_j
#               + lambda sum_i (sum_j x_ij + m_i - 1)^2 + lambda sum_j (sum_i x_ij + f_j - 1)^2
#   c_miss = 5, c_fa = 3 (repository defaults; not in the paper); lambda = 1.5 max |c| over the cost matrix.
#   Q is upper triangular; E(x) = x^T Q x excludes the constant lambda (N + M), as the paper's -92.4 does.
#
# Reference values:
#   - "Hungarian as coded": the maximum-cardinality assignment on the penalised diagonal Q entries of x_ij, scored as the sum
#     of the diagonal entries of the chosen x_ij plus the implied slack variables (hungarian_solver.py L73-L103).
#   - "GNN as coded": greedy on the same diagonal entries; scored as the sum over the chosen pairs only (gnn_solver.py).
#   - the brute-force minimum of E over all 2^n strings, and over valid associations only.
#
# C1: the rebuilt instance's Hungarian value is -92.4 (within 0.05). C4: greedy is optimal on this instance.
#
# Usage:
#     python src/p3_qantis_instance.py
#     python src/p3_qantis_instance.py --qantis-repo <path to a clone of neuraparse/qantis>   # adds the cross-check

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import itertools
import json
import math
import pathlib
import subprocess
import sys

import numpy as np
from scipy.optimize import linear_sum_assignment

RESULTS = pathlib.Path(__file__).resolve().parents[1] / "results"
PAPER_HUNGARIAN = -92.4
SEED, N_TRACKS, N_MEAS = 42, 2, 3
COVARIANCE, CLUTTER_DENSITY, GATE = 0.5, 1e-5, 9.21
C_MISS, C_FA, MULTIPLIER = 5.0, 3.0, 1.5


def generate(n_tracks: int = N_TRACKS, n_meas: int = N_MEAS, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    predicted = rng.standard_normal((n_tracks, 2))
    measurements = rng.standard_normal((n_meas, 2))
    S = np.stack([COVARIANCE * np.eye(2)] * n_tracks)
    return {"predicted": predicted, "measurements": measurements, "S": S}


def cost_matrix(scene: dict, variant: str = "code") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (costs with 0 for ungated pairs, gate mask, squared Mahalanobis distances)."""
    P, Z, S = scene["predicted"], scene["measurements"], scene["S"]
    N, M = len(P), len(Z)
    C, mask, D2 = np.zeros((N, M)), np.zeros((N, M), dtype=bool), np.zeros((N, M))
    for i in range(N):
        _, logdet = np.linalg.slogdet(2 * math.pi * S[i])
        for j in range(M):
            nu = Z[j] - P[i]
            D2[i, j] = float(nu @ np.linalg.solve(S[i], nu))
            if D2[i, j] <= GATE:
                mask[i, j] = True
                C[i, j] = 0.5 * (D2[i, j] + logdet) + (math.log(CLUTTER_DENSITY) if variant == "code" else 0.0)
    return C, mask, D2


def index_map(N: int, M: int) -> dict:
    idx = {}
    for i in range(N):
        for j in range(M):
            idx["x", i, j] = len(idx)
    for i in range(N):
        idx["m", i] = len(idx)
    for j in range(M):
        idx["f", j] = len(idx)
    return idx


def build_qubo(C: np.ndarray, mask: np.ndarray, c_miss: float = C_MISS, c_fa: float = C_FA,
               multiplier: float = MULTIPLIER, penalty: float | None = None) -> dict:
    N, M = C.shape
    idx = index_map(N, M)
    n = len(idx)
    lam = multiplier * float(np.max(np.abs(C))) if penalty is None else float(penalty)
    Q = np.zeros((n, n))
    for i in range(N):
        for j in range(M):
            if mask[i, j]:
                Q[idx["x", i, j], idx["x", i, j]] += C[i, j]
        Q[idx["m", i], idx["m", i]] += c_miss
    for j in range(M):
        Q[idx["f", j], idx["f", j]] += c_fa
    groups = [[idx["x", i, j] for j in range(M)] + [idx["m", i]] for i in range(N)]
    groups += [[idx["x", i, j] for i in range(N)] + [idx["f", j]] for j in range(M)]
    for group in groups:
        for k in group:
            Q[k, k] -= lam
        for a, b in itertools.combinations(group, 2):
            Q[min(a, b), max(a, b)] += 2 * lam
    return {"Q": Q, "penalty": lam, "offset": lam * (N + M), "N": N, "M": M, "index": idx, "groups": groups}


def energy(qubo: dict, X: np.ndarray) -> np.ndarray:
    X = np.atleast_2d(X).astype(float)
    return np.einsum("bi,ij,bj->b", X, qubo["Q"], X)


def all_strings(n: int) -> np.ndarray:
    idx = np.arange(1 << n, dtype=np.int64)
    return ((idx[:, None] >> np.arange(n)) & 1).astype(np.int8)


def violation(qubo: dict, X: np.ndarray) -> np.ndarray:
    X = np.atleast_2d(X)
    return sum((X[:, g].sum(axis=1) - 1) ** 2 for g in qubo["groups"])


def associations(N: int, M: int):
    """Every valid association: each track takes a distinct measurement or is missed."""
    for choice in itertools.product([None] + list(range(M)), repeat=N):
        used = [c for c in choice if c is not None]
        if len(used) == len(set(used)):
            yield choice


def association_vector(choice, N: int, M: int) -> np.ndarray:
    idx = index_map(N, M)
    x = np.zeros(len(idx), dtype=np.int8)
    for i, j in enumerate(choice):
        x[idx["x", i, j] if j is not None else idx["m", i]] = 1
    for j in set(range(M)) - {c for c in choice if c is not None}:
        x[idx["f", j]] = 1
    return x


def hungarian_as_coded(qubo: dict) -> dict:
    Q, N, M, idx = qubo["Q"], qubo["N"], qubo["M"], qubo["index"]
    D = np.array([[Q[idx["x", i, j], idx["x", i, j]] for j in range(M)] for i in range(N)])
    size = max(N, M)
    padded = np.full((size, size), 1e6)
    padded[:N, :M] = D
    rows, cols = linear_sum_assignment(padded)
    pairs = [(int(r), int(c)) for r, c in zip(rows, cols) if r < N and c < M]
    choice = tuple(dict(pairs).get(i) for i in range(N))
    x = association_vector(choice, N, M)
    return {"association": choice, "objective": float(np.sum(np.diag(Q)[x == 1])), "vector": x}


def gnn_as_coded(qubo: dict) -> dict:
    Q, N, M, idx = qubo["Q"], qubo["N"], qubo["M"], qubo["index"]
    D = np.array([[Q[idx["x", i, j], idx["x", i, j]] for j in range(M)] for i in range(N)])
    used_t, used_m, pairs = set(), set(), []
    for flat in np.argsort(D, axis=None):
        i, j = divmod(int(flat), M)
        if i in used_t or j in used_m:
            continue
        pairs.append((i, j))
        used_t.add(i)
        used_m.add(j)
    choice = tuple(dict(pairs).get(i) for i in range(N))
    x = association_vector(choice, N, M)
    return {"association": choice, "objective_pairs_only": float(sum(D[i, j] for i, j in pairs)),
            "objective_full": float(energy(qubo, x)[0]), "vector": x}


def brute_force(qubo: dict) -> dict:
    n = qubo["Q"].shape[0]
    X = all_strings(n)
    E = energy(qubo, X)
    V = violation(qubo, X)
    order = np.argsort(E, kind="stable")
    best = int(order[0])
    feasible = V == 0
    fbest = int(np.flatnonzero(feasible)[np.argmin(E[feasible])])
    return {"strings": X, "energies": E, "violations": V, "min_energy": float(E[best]), "argmin": X[best],
            "argmin_feasible": bool(V[best] == 0), "min_feasible_energy": float(E[fbest]), "feasible_argmin": X[fbest],
            "ground_degeneracy": int(np.sum(np.isclose(E, E[best], atol=1e-9))),
            "second_distinct_energy": float(np.min(E[~np.isclose(E, E[best], atol=1e-9)])),
            "feasible_count": int(feasible.sum())}


def decode(x: np.ndarray, qubo: dict) -> dict:
    inv = {v: k for k, v in qubo["index"].items()}
    return {"selected": ["%s%s" % (inv[k][0], "".join(str(t) for t in inv[k][1:])) for k in np.flatnonzero(x)]}


def study(variant: str) -> dict:
    scene = generate()
    C, mask, D2 = cost_matrix(scene, variant)
    qubo = build_qubo(C, mask)
    hung = hungarian_as_coded(qubo)
    gnn = gnn_as_coded(qubo)
    bf = brute_force(qubo)
    feasible_min = min(float(energy(qubo, association_vector(a, qubo["N"], qubo["M"]))[0])
                       for a in associations(qubo["N"], qubo["M"]))
    return {
        "variant": variant, "scene": {k: v.tolist() for k, v in scene.items()},
        "costs": C.tolist(), "gate_mask": mask.tolist(), "mahalanobis2": D2.tolist(),
        "penalty": qubo["penalty"], "offset": qubo["offset"], "variables": int(qubo["Q"].shape[0]),
        "quadratic_terms": int(np.count_nonzero(np.triu(qubo["Q"], 1))),
        "hungarian_as_coded": {"association": list(hung["association"]), "objective": hung["objective"],
                               "qubo_energy": float(energy(qubo, hung["vector"])[0])},
        "gnn_as_coded": {"association": list(gnn["association"]), "objective_pairs_only": gnn["objective_pairs_only"],
                         "objective_full": gnn["objective_full"]},
        "brute_force": {"min_energy": bf["min_energy"], "argmin": decode(bf["argmin"], qubo), "argmin_feasible": bf["argmin_feasible"],
                        "min_feasible_energy": bf["min_feasible_energy"], "feasible_argmin": decode(bf["feasible_argmin"], qubo),
                        "ground_degeneracy": bf["ground_degeneracy"], "second_distinct_energy": bf["second_distinct_energy"],
                        "feasible_strings": bf["feasible_count"], "min_over_enumerated_associations": feasible_min},
        "Q": qubo["Q"].tolist(),
    }


def cross_check(repo: pathlib.Path, ours: dict, n_tracks: int = N_TRACKS, n_meas: int = N_MEAS) -> dict:
    """Build the same instance with the repository's own code (run from its clone) and compare."""
    src = repo / "packages" / "quantum-mht" / "src"
    sys.path.insert(0, str(src))
    from quantum_mht.formulation.mtda_qubo_builder import MTDAQuboBuilder  # noqa: E402

    rng = np.random.default_rng(SEED)
    predicted = rng.standard_normal((n_tracks, 2)).astype(np.float64)
    measurements = rng.standard_normal((n_meas, 2)).astype(np.float64)
    covariances = np.stack([np.eye(2, dtype=np.float64) * COVARIANCE] * n_tracks)
    theirs = MTDAQuboBuilder().build(predicted, measurements, covariances)

    def load(name, path):  # bypass classical_solvers/__init__.py, which imports optional heavy solvers
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module  # dataclasses look the module up while the class is being created
        spec.loader.exec_module(module)
        return module

    solvers = src / "quantum_mht" / "solvers" / "classical_solvers"
    hung = load("qantis_hungarian", solvers / "hungarian_solver.py").HungarianSolver().solve(theirs)
    gnn = load("qantis_gnn", solvers / "gnn_solver.py").GNNSolver().solve(theirs)

    Q_theirs = np.zeros((theirs.num_variables, theirs.num_variables))
    for (a, b), v in theirs.Q.items():
        Q_theirs[a, b] += v
    Q_ours = np.array(ours["Q"])
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return {
        "repository_commit": commit,
        "Q_max_abs_difference": float(np.max(np.abs(Q_theirs - Q_ours))),
        "penalty_theirs": float(theirs.penalty), "penalty_ours": ours["penalty"],
        "hungarian_theirs": float(hung.objective_value), "hungarian_ours": ours["hungarian_as_coded"]["objective"],
        "hungarian_assignments_theirs": hung.assignments, "hungarian_missed_theirs": hung.missed_detections,
        "hungarian_false_alarms_theirs": hung.false_alarms,
        "gnn_theirs": float(gnn.objective_value), "gnn_assignments_theirs": gnn.assignments,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qantis-repo", type=str, default=None)
    args = parser.parse_args()

    record = {"timestamp": dt.datetime.now().astimezone().isoformat(), "experiment": "P3.1 QANTIS instance, C1 and C4",
              "paper_hungarian": PAPER_HUNGARIAN, "settings": {"seed": SEED, "N": N_TRACKS, "M": N_MEAS,
              "covariance": COVARIANCE, "clutter_density": CLUTTER_DENSITY, "gate": GATE, "c_miss": C_MISS, "c_fa": C_FA,
              "penalty_multiplier": MULTIPLIER}, "variants": {}}
    for variant in ("code", "paper"):
        s = study(variant)
        record["variants"][variant] = s
        h, g, b = s["hungarian_as_coded"], s["gnn_as_coded"], s["brute_force"]
        print("== cost variant: %s ==" % variant)
        print("  costs %s  gated %s" % (np.round(s["costs"], 3).tolist(), s["gate_mask"]))
        print("  lambda %.4f  variables %d  quadratic terms %d" % (s["penalty"], s["variables"], s["quadratic_terms"]))
        print("  Hungarian as coded: association %s  objective %.4f  (QUBO energy %.4f)" % (h["association"], h["objective"], h["qubo_energy"]))
        print("  GNN as coded      : association %s  pairs-only %.4f  full %.4f" % (g["association"], g["objective_pairs_only"], g["objective_full"]))
        print("  brute force       : min %.4f  argmin %s feasible %s  degeneracy %d  next level %.4f" % (
            b["min_energy"], b["argmin"]["selected"], b["argmin_feasible"], b["ground_degeneracy"], b["second_distinct_energy"]))
        print("                      min over valid associations %.4f (%s)" % (b["min_over_enumerated_associations"], b["feasible_argmin"]["selected"]))

    code = record["variants"]["code"]
    hung = code["hungarian_as_coded"]
    same_as_optimum = abs(hung["qubo_energy"] - code["brute_force"]["min_over_enumerated_associations"]) <= 1e-9
    diff = abs(hung["objective"] - PAPER_HUNGARIAN)
    c1 = "reproduced" if diff <= 0.05 else ("partly reproduced" if same_as_optimum else "not reproduced")
    gnn_opt = abs(code["gnn_as_coded"]["objective_full"] - code["brute_force"]["min_over_enumerated_associations"]) <= 1e-9
    c4 = "reproduced" if gnn_opt else "not reproduced"
    record["grades"] = {"C1": c1, "C1_difference": diff, "C1_hungarian_is_qubo_optimum": same_as_optimum, "C4": c4}
    print("C1 %s (|%.4f - %.1f| = %.4f; Hungarian association is the QUBO optimum over valid associations: %s)"
          % (c1, hung["objective"], PAPER_HUNGARIAN, diff, same_as_optimum))
    print("C4 %s" % c4)

    if args.qantis_repo:
        cc = cross_check(pathlib.Path(args.qantis_repo), code)
        record["cross_check"] = cc
        print("cross-check with repository %s: max |Q diff| %.2e, penalty %.6f vs %.6f, Hungarian %.6f vs %.6f, GNN %.6f"
              % (cc["repository_commit"][:7], cc["Q_max_abs_difference"], cc["penalty_theirs"], cc["penalty_ours"],
                 cc["hungarian_theirs"], cc["hungarian_ours"], cc["gnn_theirs"]))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p3_1-instance-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps(record, indent=2, default=lambda v: v.item() if isinstance(v, np.generic) else str(v)),
                   encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
