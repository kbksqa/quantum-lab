# P5.0 - Constraint-preserving mixers for assignment: circuits, simulator and the hard gates G1-G3 (docs/p5-plan.md).
#
# Qubit k = i * n + j is cell (row i, column j) of a pure n x n assignment. Basis index = sum_k x_k 2^k, Qiskit's order.
#
# Ansatze:
#   xpen  P1.4 as stored: uniform start, X mixer, cost + A (row and column violations)^2, A = max|c|
#   rxy   start: a W state on every row. Mixer: for each row, on every pair of its qubits in lexicographic order,
#         exp(-i beta (|01><10| + |10><01|)). Phase: cost + A (column violations)^2, A = max|c|.
#   perm  start: uniform over the n! permutations. Mixer: for rows i < i' and columns j < j', in lexicographic order,
#         exp(-i beta (|abcd = 1100><0011| + h.c.)) with a = (i, j), b = (i', j'), c = (i, j'), d = (i', j), which swaps the
#         columns of two rows. Phase: cost only.
# The phase operator is the Ising form of the energy divided by its largest coefficient, constants dropped, as in P1.4.
# The simulator applies exactly the gate product that the circuit contains, not the exponential of a summed Hamiltonian.
#
# Circuits: an XY pair is XXPlusYYGate(2 beta). A perm rotation is CX(a, b) CX(a, c) CX(a, d), then RX(2 beta) on a controlled
# by b = 0, c = 1, d = 1, then the three CX again: the CX gates map 1100 to 1011 and leave 0011 alone, so the controlled RX
# mixes exactly those two states. State preparation uses Qiskit's generic StatePreparation; gate counts are upper bounds.
#
# Gates:
#   G1  transpiled circuit statevector == simulator to 1e-9 after removing the global phase
#   G2  probability outside the preserved space < 1e-12 for random angles
#   G3  the P1.4 instances and stored angles reproduce P1.4's optima and P(optimal) to 1e-9
#
# P5.1 (study): R-XY and PERM optimised as in P1.4 (COBYLA on <H>, 6 random starts plus an interpolated start, depths 1-3)
# on the 50 + 50 P1.4 instances; X+pen taken from the stored P1.4 angles. Gate counts for the first 5 instances of each size
# on the P1.4 heavy-hex CZ model. H1-H4 and the hardware go rule are graded on pure 3x3 exactly as registered.
#
# Usage:
#     python src/p5_mixers.py gates
#     python src/p5_mixers.py study

from __future__ import annotations

import argparse
import datetime as dt
import json
import math

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import RXGate, StatePreparation, XXPlusYYGate
from qiskit.quantum_info import Statevector

from p1_5_hardware import P1_4_FILE, distribution_metrics, rebuild_p1_4_instances
from p1_annealing import max_abs_rule
from p1_penalty import enumerate_strings
from p1_qaoa import DEPTHS, ising, ising_energies, qaoa_circuit, simulate as simulate_x
from p1_qaoa import prepare as prepare_x
from p1_qubo import build_qubo, hungarian_cost
from p1_scenario import RESULTS

ANSATZE = ("xpen", "rxy", "perm")
SIZES = {"pure 2x2": 2, "pure 3x3": 3}
BASIS = ["u", "cx", "rz", "rx", "ry", "rzz", "h", "x", "sx"]


# ---------------------------------------------------------------- spaces

def bits(n: int) -> np.ndarray:
    idx = np.arange(1 << (n * n), dtype=np.int64)
    return ((idx[:, None] >> np.arange(n * n)) & 1).astype(np.int16)


def spaces(n: int) -> dict:
    grid = bits(n).reshape(-1, n, n)
    row_one_hot = np.all(grid.sum(axis=2) == 1, axis=1)
    permutation = row_one_hot & np.all(grid.sum(axis=1) == 1, axis=1)
    return {"xpen": np.ones(len(grid), dtype=bool), "rxy": row_one_hot, "perm": permutation}


def initial_state(n: int, ansatz: str) -> np.ndarray:
    support = spaces(n)[ansatz]
    psi = support.astype(complex)
    return psi / math.sqrt(support.sum())


def rxy_pairs(n: int) -> list:
    return [(i * n + j, i * n + k) for i in range(n) for j in range(n) for k in range(j + 1, n)]


def perm_quads(n: int) -> list:
    """(a, b, c, d) = ((i, j), (i', j'), (i, j'), (i', j)) for i < i', j < j', lexicographic."""
    return [(i * n + j, r * n + k, i * n + k, r * n + j)
            for i in range(n) for r in range(i + 1, n) for j in range(n) for k in range(j + 1, n)]


# ---------------------------------------------------------------- energies and phase operator

def energies(C: np.ndarray, ansatz: str, A: float) -> np.ndarray:
    n = C.shape[0]
    grid = bits(n).reshape(-1, n, n)
    cost = grid.reshape(len(grid), -1).astype(float) @ C.reshape(-1)
    rows = ((grid.sum(axis=2) - 1) ** 2).sum(axis=1)
    cols = ((grid.sum(axis=1) - 1) ** 2).sum(axis=1)
    if ansatz == "xpen":
        return cost + A * (rows + cols)
    if ansatz == "rxy":
        return cost + A * cols
    return cost


def qubo(C: np.ndarray, ansatz: str, A: float) -> dict:
    n = C.shape[0]
    if ansatz == "xpen":
        return build_qubo(C, penalty=A)
    m = n * n
    Q = np.zeros((m, m))
    for k in range(m):
        Q[k, k] = C.reshape(-1)[k]
    offset = 0.0
    if ansatz == "rxy":
        for k in range(m):
            Q[k, k] -= A
        for j in range(n):
            column = [i * n + j for i in range(n)]
            for a in range(n):
                for b in range(a + 1, n):
                    Q[column[a], column[b]] += 2.0 * A
        offset = n * A
    return {"Q": Q, "offset": offset}


def prepare(C: np.ndarray, ansatz: str, A: float) -> dict:
    h, J, const = ising(qubo(C, ansatz, A))
    scale = max(float(np.abs(h).max()), max((abs(v) for v in J.values()), default=0.0))
    E = energies(C, ansatz, A)
    if not np.allclose(ising_energies(h, J, const, bits(C.shape[0])), E, atol=1e-9 * max(1.0, float(np.abs(E).max()))):
        raise SystemExit("Ising form does not reproduce the %s energies - stop" % ansatz)
    return {"h": h, "J": J, "const": const, "scale": scale, "energies": E, "diag": (E - const) / scale, "A": A}


# ---------------------------------------------------------------- simulator

_PAIRS: dict = {}


def rotation_indices(size: int, ones: tuple, zeros: tuple) -> tuple[np.ndarray, np.ndarray]:
    key = (size, ones, zeros)
    if key not in _PAIRS:
        idx = np.arange(size, dtype=np.int64)
        one, zero = sum(1 << q for q in ones), sum(1 << q for q in zeros)
        src = idx[((idx & one) == one) & ((idx & zero) == 0)]
        _PAIRS[key] = (src, src ^ (one | zero))
    return _PAIRS[key]


def rotate(psi: np.ndarray, ones: tuple, zeros: tuple, beta: float) -> None:
    """exp(-i beta (|ones=1, zeros=0><ones=0, zeros=1| + h.c.)) in place; all other basis states unchanged."""
    src, dst = rotation_indices(len(psi), tuple(ones), tuple(zeros))
    c, s = math.cos(beta), -1j * math.sin(beta)
    a, b = psi[src].copy(), psi[dst].copy()
    psi[src] = c * a + s * b
    psi[dst] = s * a + c * b


def mixer(psi: np.ndarray, n: int, ansatz: str, beta: float) -> None:
    if ansatz == "rxy":
        for k, l in rxy_pairs(n):
            rotate(psi, (k,), (l,), beta)
    elif ansatz == "perm":
        for a, b, c, d in perm_quads(n):
            rotate(psi, (a, b), (c, d), beta)
    else:
        raise ValueError(ansatz)


def evolve(diag: np.ndarray, n: int, ansatz: str, gammas, betas) -> np.ndarray:
    """Statevector of the ansatz. xpen uses the P1.4 simulator's convention (uniform start, X mixer)."""
    if ansatz == "xpen":
        psi = np.full(1 << (n * n), 1 / math.sqrt(1 << (n * n)), dtype=complex)
        for gamma, beta in zip(gammas, betas):
            psi = psi * np.exp(-1j * gamma * diag)
            c, s = math.cos(beta), -1j * math.sin(beta)
            t = psi.reshape([2] * (n * n))
            for axis in range(n * n):
                t0, t1 = np.take(t, 0, axis=axis), np.take(t, 1, axis=axis)
                t = np.stack([c * t0 + s * t1, s * t0 + c * t1], axis=axis)
            psi = t.reshape(-1)
        return psi
    psi = initial_state(n, ansatz)
    for gamma, beta in zip(gammas, betas):
        psi = psi * np.exp(-1j * gamma * diag)
        mixer(psi, n, ansatz, beta)
    return psi


def probabilities(diag: np.ndarray, n: int, ansatz: str, gammas, betas) -> np.ndarray:
    return np.abs(evolve(diag, n, ansatz, gammas, betas)) ** 2


# ---------------------------------------------------------------- circuits

def perm_rotation(qc: QuantumCircuit, quad: tuple, beta: float) -> None:
    a, b, c, d = quad
    for target in (b, c, d):
        qc.cx(a, target)
    qc.append(RXGate(2.0 * beta).control(3, ctrl_state=0b110, annotated=False), [b, c, d, a])
    for target in (d, c, b):
        qc.cx(a, target)


def circuit(n: int, ansatz: str, prep: dict, gammas, betas, measure: bool = False) -> QuantumCircuit:
    if ansatz == "xpen":
        return qaoa_circuit(prep["h"], prep["J"], prep["scale"], gammas, betas, measure=measure)
    m = n * n
    qc = QuantumCircuit(m)
    if ansatz == "rxy":
        w = np.zeros(1 << n)
        w[[1 << j for j in range(n)]] = 1 / math.sqrt(n)
        for i in range(n):
            qc.append(StatePreparation(w), [i * n + j for j in range(n)])
    else:
        qc.append(StatePreparation(initial_state(n, "perm")), list(range(m)))
    h, J, scale = prep["h"], prep["J"], prep["scale"]
    for gamma, beta in zip(gammas, betas):
        for k in range(m):
            if h[k] != 0.0:
                qc.rz(2.0 * gamma * h[k] / scale, k)
        for (k, l), j in J.items():
            qc.rzz(2.0 * gamma * j / scale, k, l)
        if ansatz == "rxy":
            for k, l in rxy_pairs(n):
                qc.append(XXPlusYYGate(2.0 * beta, 0.0), [k, l])
        else:
            for quad in perm_quads(n):
                perm_rotation(qc, quad, beta)
    if measure:
        qc.measure_all()
    return qc


def circuit_statevector(qc: QuantumCircuit) -> np.ndarray:
    return Statevector(transpile(qc, basis_gates=BASIS, optimization_level=0)).data


def phase_aligned_difference(reference: np.ndarray, other: np.ndarray) -> float:
    overlap = np.vdot(other, reference)
    phase = overlap / abs(overlap) if abs(overlap) > 0 else 1.0
    return float(np.max(np.abs(reference - other * phase)))


# ---------------------------------------------------------------- gates

def g3_rebuild() -> tuple[dict, dict]:
    stored = json.loads(P1_4_FILE.read_text(encoding="utf-8"))
    instances = rebuild_p1_4_instances()
    report = {}
    for size, n in SIZES.items():
        detail = stored["results"][size]["instances_detail"]
        worst_optimum = worst_p = 0.0
        for index, record in enumerate(detail):
            C = instances[size][index]
            optimum = hungarian_cost(C)
            worst_optimum = max(worst_optimum, abs(optimum - record["optimum"]))
            A = record["max_abs"]["A"]
            if abs(max_abs_rule(C) - A) > 1e-12:
                raise SystemExit("G3: penalty of %s instance %d differs from P1.4 - stop" % (size, index))
            strings = enumerate_strings(C)
            reference = prepare_x(C, A, strings)
            ours = prepare(C, "xpen", A)
            if not np.allclose(ours["energies"], reference["energies"]) or not np.allclose(ours["diag"], reference["diag"]):
                raise SystemExit("G3: xpen energies differ from P1.4 for %s instance %d - stop" % (size, index))
            if not np.array_equal(strings["V"] == 0, spaces(n)["perm"]):
                raise SystemExit("G3: permutation mask differs from P1's feasibility for %s - stop" % size)
            for p in DEPTHS:
                s = record["max_abs"]["p%d" % p]
                again = distribution_metrics(simulate_x(reference["diag"], n * n, s["gammas"], s["betas"]), strings, optimum)
                ours_p = distribution_metrics(probabilities(ours["diag"], n, "xpen", s["gammas"], s["betas"]), strings, optimum)
                worst_p = max(worst_p, abs(again["p_optimal"] - s["p_optimal"]), abs(ours_p["p_optimal"] - s["p_optimal"]))
        report[size] = {"instances": len(detail), "max_optimum_difference": worst_optimum,
                        "max_p_optimal_difference": worst_p, "passed": worst_optimum <= 1e-9 and worst_p <= 1e-9}
    return report, instances


def g1_g2(instances: dict, per_size: int, seed: int) -> tuple[dict, dict]:
    rng = np.random.default_rng(seed)
    g1, g2 = {}, {}
    for size, n in SIZES.items():
        space = spaces(n)
        worst_state, worst_leak = 0.0, {"rxy": 0.0, "perm": 0.0}
        checked = 0
        for index in range(per_size):
            C = instances[size][index]
            A = max_abs_rule(C)
            for ansatz in ANSATZE:
                prep = prepare(C, ansatz, A)
                for p in DEPTHS:
                    gammas, betas = rng.uniform(0, math.pi, p), rng.uniform(0, math.pi, p)
                    psi = evolve(prep["diag"], n, ansatz, gammas, betas)
                    worst_state = max(worst_state, phase_aligned_difference(
                        psi, circuit_statevector(circuit(n, ansatz, prep, gammas, betas))))
                    checked += 1
                    if ansatz != "xpen":
                        leak = 1.0 - float(np.sum(np.abs(psi[space[ansatz]]) ** 2))
                        worst_leak[ansatz] = max(worst_leak[ansatz], abs(leak))
        g1[size] = {"circuits_checked": checked, "max_amplitude_difference": worst_state, "passed": worst_state <= 1e-9}
        g2[size] = {"max_probability_outside": worst_leak, "passed": all(v < 1e-12 for v in worst_leak.values()),
                    "space_sizes": {k: int(v.sum()) for k, v in space.items()}}
        print("  %s: G1 %d circuits, max |difference| %.2e; G2 outside %s" % (size, checked, worst_state, worst_leak),
              flush=True)
    return g1, g2


# ---------------------------------------------------------------- P5.1: simulator study, H1-H4 and the go rule

MAX_CZ = 60
RESOURCE_INSTANCES = 5


def optimize(diag: np.ndarray, n: int, ansatz: str, p: int, rng, starts: int, warm) -> tuple[np.ndarray, float]:
    """P1.4's optimiser with this module's simulator: COBYLA on <H>, the same start ranges and options."""
    from scipy.optimize import minimize

    def objective(v):
        return float(probabilities(diag, n, ansatz, v[:p], v[p:]) @ diag)

    initial = [np.concatenate([rng.uniform(0, math.pi, p), rng.uniform(0, math.pi / 2, p)]) for _ in range(starts)]
    if warm is not None:
        initial.insert(0, warm)
    best = None
    for x0 in initial:
        res = minimize(objective, x0, method="COBYLA", options={"maxiter": 300, "rhobeg": 0.3})
        if best is None or res.fun < best.fun:
            best = res
    return np.asarray(best.x), float(best.fun)


def optimal_mask(C: np.ndarray, optimum: float) -> np.ndarray:
    n = C.shape[0]
    cost = energies(C, "perm", 0.0)
    return spaces(n)["perm"] & (np.abs(cost - optimum) <= 1e-6 * max(1.0, abs(optimum)))


def baselines(C: np.ndarray, optimum: float) -> dict:
    """Guessing baselines: uniform over all strings, and uniform over each ansatz's own search space."""
    n = C.shape[0]
    optimal = optimal_mask(C, optimum)
    space = spaces(n)
    return {"all_strings": float(optimal.mean()),
            **{ansatz: float(optimal[space[ansatz]].sum() / space[ansatz].sum()) for ansatz in ANSATZE}}


def two_qubit_gates(qc: QuantumCircuit) -> dict:
    from p1_qaoa import heavy_hex_backend

    compiled = transpile(qc, backend=heavy_hex_backend(), optimization_level=3, seed_transpiler=7)
    return {"two_qubit_gates": int(compiled.count_ops().get("cz", 0)), "transpiled_depth": compiled.depth()}


def study_instance(size: str, index: int, C: np.ndarray, stored: dict, rng, starts: int, resources: bool) -> dict:
    from p1_qaoa import interpolate

    n = SIZES[size]
    optimum = hungarian_cost(C)
    if abs(optimum - stored["optimum"]) > 1e-9:
        raise SystemExit("%s instance %d does not match P1.4 - stop" % (size, index))
    A = stored["max_abs"]["A"]
    optimal = optimal_mask(C, optimum)
    feasible = spaces(n)["perm"]
    base = baselines(C, optimum)
    row = {"index": index, "optimum": optimum, "A": A, "optimal_strings": int(optimal.sum()), "baselines": base,
           "ansatze": {}}
    for ansatz in ANSATZE:
        prep = prepare(C, ansatz, A)
        per_depth, warm = {}, None
        for p in DEPTHS:
            key = "p%d" % p
            if ansatz == "xpen":
                s = stored["max_abs"][key]
                gammas, betas, expectation = np.array(s["gammas"]), np.array(s["betas"]), s["expectation_scaled"]
            else:
                params, expectation = optimize(prep["diag"], n, ansatz, p, rng, starts, warm)
                gammas, betas = params[:p], params[p:]
                warm = interpolate(params, p, p + 1)
            probs = probabilities(prep["diag"], n, ansatz, gammas, betas)
            result = {"p_optimal": float(probs[optimal].sum()), "p_feasible": float(probs[feasible].sum()),
                      "lift_over_own_space": float(probs[optimal].sum()) / base[ansatz],
                      "expectation_scaled": expectation, "gammas": list(map(float, gammas)), "betas": list(map(float, betas))}
            if ansatz == "xpen" and abs(result["p_optimal"] - stored["max_abs"][key]["p_optimal"]) > 1e-9:
                raise SystemExit("stored X+pen angles do not reproduce P1.4 for %s instance %d %s - stop" % (size, index, key))
            if resources:
                result["resources"] = two_qubit_gates(circuit(n, ansatz, prep, gammas, betas, measure=True))
            per_depth[key] = result
        row["ansatze"][ansatz] = per_depth
    return row


def paired(rows: list, first: str, second: str, key: str) -> dict:
    d = np.array([r["ansatze"][first][key]["p_optimal"] - r["ansatze"][second][key]["p_optimal"] for r in rows])
    return {"n": len(d), "mean": float(d.mean()), "sem": float(d.std(ddof=1) / math.sqrt(len(d))),
            "positive_share": float(np.mean(d > 0))}


def grade_difference(diffs: dict) -> str:
    """H1 / H2: held if positive and > 2 s.e. at every depth; partly held if positive at every depth; failed otherwise."""
    if all(d["mean"] > 0 and d["mean"] > 2 * d["sem"] for d in diffs.values()):
        return "held"
    if all(d["mean"] > 0 for d in diffs.values()):
        return "partly held"
    return "failed"


def grade_lift(lifts: np.ndarray) -> dict:
    """H3: held if the mean lift at p = 3 exceeds 1 by more than 2 s.e.; partly held if it exceeds 1; failed otherwise."""
    mean, sem = float(lifts.mean()), float(lifts.std(ddof=1) / math.sqrt(len(lifts)))
    grade = "held" if mean - 1 > 2 * sem else ("partly held" if mean > 1 else "failed")
    return {"mean": mean, "sem": sem, "grade": grade}


def summarise(rows: list, n: int) -> dict:
    out = {}
    for ansatz in ANSATZE:
        for p in DEPTHS:
            key = "p%d" % p
            values = [r["ansatze"][ansatz][key] for r in rows]
            cz = [v["resources"]["two_qubit_gates"] for v in values if "resources" in v]
            out["%s %s" % (ansatz, key)] = {
                "p_optimal_mean": float(np.mean([v["p_optimal"] for v in values])),
                "p_optimal_sem": float(np.std([v["p_optimal"] for v in values], ddof=1) / math.sqrt(len(values))),
                "p_feasible_mean": float(np.mean([v["p_feasible"] for v in values])),
                "lift_mean": float(np.mean([v["lift_over_own_space"] for v in values])),
                "own_space_baseline_mean": float(np.mean([r["baselines"][ansatz] for r in rows])),
                "median_cz_first_instances": float(np.median(cz)) if cz else None,
                "cz_first_instances": cz,
            }
    out["all_strings_baseline_mean"] = float(np.mean([r["baselines"]["all_strings"] for r in rows]))
    return out


def verdicts(rows: list, summary: dict) -> dict:
    h1 = {key: paired(rows, "rxy", "xpen", key) for key in ("p1", "p2", "p3")}
    h2 = {key: paired(rows, "perm", "rxy", key) for key in ("p1", "p2", "p3")}
    h3 = grade_lift(np.array([r["ansatze"]["perm"]["p3"]["lift_over_own_space"] for r in rows]))
    candidates = [{"config": name, **{k: v for k, v in s.items() if k != "cz_first_instances"}}
                  for name, s in summary.items() if isinstance(s, dict) and s["median_cz_first_instances"] is not None
                  and s["median_cz_first_instances"] <= MAX_CZ]
    best = max(candidates, key=lambda c: c["p_optimal_mean"]) if candidates else None
    preserving_within = [c for c in candidates if not c["config"].startswith("xpen")]
    h4 = "held" if best is not None and not best["config"].startswith("xpen") and preserving_within else "failed"
    xpen_within = [c for c in candidates if c["config"].startswith("xpen")]
    best_xpen = max((c["p_optimal_mean"] for c in xpen_within), default=None)
    go = [c for c in preserving_within if best_xpen is not None and c["p_optimal_mean"] >= 2 * best_xpen
          and c["lift_mean"] >= 1.5]
    return {
        "H1_rxy_minus_xpen": {"by_depth": h1, "grade": grade_difference(h1)},
        "H2_perm_minus_rxy": {"by_depth": h2, "grade": grade_difference(h2)},
        "H3_perm_lift_p3": h3,
        "H4_best_within_budget": {"candidates": candidates, "best": best, "grade": h4},
        "go_rule": {"best_xpen_within_budget": best_xpen, "passing_configs": [c["config"] for c in go], "go": bool(go),
                    "note": None if xpen_within else "no X+pen configuration within the budget; the go rule cannot be met"},
    }


def study(starts: int, seed: int) -> dict:
    stored = json.loads(P1_4_FILE.read_text(encoding="utf-8"))
    instances = rebuild_p1_4_instances()
    out = {}
    for s_index, (size, n) in enumerate(SIZES.items()):
        detail = stored["results"][size]["instances_detail"]
        rows = []
        for index, record in enumerate(detail):
            rng = np.random.default_rng([seed, s_index, index])
            rows.append(study_instance(size, index, instances[size][index], record, rng, starts,
                                       resources=index < RESOURCE_INSTANCES))
            if (index + 1) % 10 == 0:
                print("  %s: %d / %d instances" % (size, index + 1, len(detail)), flush=True)
        summary = summarise(rows, n)
        out[size] = {"summary": summary, "instances_detail": rows}
        for name, s in summary.items():
            if isinstance(s, dict):
                print("  %-9s %-8s P(opt) %.4f +- %.4f  P(feasible) %.4f  lift %.2f (own baseline %.4f)  median CZ %s"
                      % (size, name, s["p_optimal_mean"], s["p_optimal_sem"], s["p_feasible_mean"], s["lift_mean"],
                         s["own_space_baseline_mean"], s["median_cz_first_instances"]))
    out["verdicts_pure_3x3"] = verdicts(out["pure 3x3"]["instances_detail"], out["pure 3x3"]["summary"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("gates")
    g.add_argument("--per-size", type=int, default=5)
    g.add_argument("--seed", type=int, default=2050)
    s = sub.add_parser("study")
    s.add_argument("--starts", type=int, default=6)
    s.add_argument("--seed", type=int, default=2051)
    args = parser.parse_args()

    if args.command == "study":
        result = study(args.starts, args.seed)
        v = result["verdicts_pure_3x3"]
        print("H1 %s  H2 %s  H3 %s  H4 %s  go %s" % (v["H1_rxy_minus_xpen"]["grade"], v["H2_perm_minus_rxy"]["grade"],
                                                   v["H3_perm_lift_p3"]["grade"], v["H4_best_within_budget"]["grade"],
                                                   v["go_rule"]["go"]))
        print(json.dumps({k: val for k, val in v.items() if k != "H4_best_within_budget"}, indent=1))
        print("H4 best: %s" % v["H4_best_within_budget"]["best"])
        RESULTS.mkdir(exist_ok=True)
        out = RESULTS / ("p5_1-study-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
        out.write_text(json.dumps({"timestamp": dt.datetime.now().astimezone().isoformat(),
                                   "experiment": "P5.1 simulator study: constraint-preserving mixers against X+pen",
                                   "seed": args.seed, "starts": args.starts, "depths": DEPTHS, "max_cz_rule": MAX_CZ,
                                   "resources_note": "heavy-hex (distance 3) CZ model, optimisation level 3, seed 7, "
                                                     "first %d instances, generic state preparation - upper bounds"
                                                     % RESOURCE_INSTANCES,
                                   **result}, indent=2), encoding="utf-8")
        print("saved " + str(out))
        return

    print("G3: rebuild the P1.4 instances and stored angles")
    g3, instances = g3_rebuild()
    print("  %s" % g3)
    print("G1 / G2: circuits against the simulator, and leakage, with random angles")
    g1, g2 = g1_g2(instances, args.per_size, args.seed)
    passed = all(r["passed"] for gate in (g1, g2, g3) for r in gate.values())
    print("GATES %s" % ("PASSED" if passed else "FAILED"))
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p5_0-gates-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps({"timestamp": dt.datetime.now().astimezone().isoformat(),
                               "experiment": "P5.0 gates G1-G3 for constraint-preserving mixers", "seed": args.seed,
                               "per_size": args.per_size, "G1": g1, "G2": g2, "G3": g3, "passed": passed},
                              indent=2), encoding="utf-8")
    print("saved " + str(out))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
