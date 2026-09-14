# P1.4 - QAOA on a simulator for small assignment QUBOs (pure 2x2 = 4 qubits, pure 3x3 = 9 qubits).
#
# QUBO -> Ising with x = (1 - z) / 2  (|0> means z = +1 means x = 0):
#   Q_kk x_k          ->  -Q_kk/2 z_k            + Q_kk/2
#   Q_kl x_k x_l      ->  -Q_kl/4 (z_k + z_l) + Q_kl/4 z_k z_l + Q_kl/4
# Coefficients are divided by scale = max |h|, |J| so that angle ranges are comparable across instances.
#
# QAOA layer: exp(-i gamma H / scale) then exp(-i beta sum X).
#   circuit: RZ(2 gamma h_k / scale), RZZ(2 gamma J_kl / scale), RX(2 beta)
#   simulator: the cost part is diagonal, so the state is multiplied by exp(-i gamma E(x) / scale) and the mixer is
#   applied qubit by qubit. The simulator is checked against Qiskit's Statevector in the tests.
#
# Parameters: COBYLA minimising <H>, several random starts, and for depth p > 1 an extra start interpolated from the
# best depth p - 1 schedule. Penalties compared: A = max|c| (computable) and A = 1.5 x A_crit (oracle from P1.2).
# The 3x3 instances are the P1.2 / P1.3 instance set, so annealing numbers from P1.3 apply to the same instances.
#
# Metrics (pre-registered in docs/p1-plan.md): P(optimal), P(feasible), best feasible cost in 1024 samples divided
# by the optimum, and circuit resources after transpiling to a heavy-hex CZ model (an estimate, not a real device).
#
# Usage:
#     python src/p1_qaoa.py
#     python src/p1_qaoa.py --instances 50 --starts 6 --shots 1024

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math

import numpy as np
from qiskit import QuantumCircuit, transpile
from scipy.optimize import minimize

from p1_annealing import max_abs_rule, p1_2_instances
from p1_penalty import critical_penalty, enumerate_strings
from p1_qubo import build_qubo, hungarian_cost
from p1_scenario import RESULTS, Params, generate, pure_cost

DEPTHS = [1, 2, 3]


def ising(qubo: dict) -> tuple[np.ndarray, dict, float]:
    Q = qubo["Q"]
    m = Q.shape[0]
    h = np.zeros(m)
    J = {}
    const = float(qubo["offset"])
    for k in range(m):
        h[k] -= Q[k, k] / 2.0
        const += Q[k, k] / 2.0
    for k in range(m):
        for l in range(k + 1, m):
            q = Q[k, l]
            if q != 0.0:
                J[(k, l)] = q / 4.0
                h[k] -= q / 4.0
                h[l] -= q / 4.0
                const += q / 4.0
    return h, J, const


def ising_energies(h: np.ndarray, J: dict, const: float, X: np.ndarray) -> np.ndarray:
    Z = 1.0 - 2.0 * X.astype(float)
    E = const + Z @ h
    for (k, l), j in J.items():
        E = E + j * Z[:, k] * Z[:, l]
    return E


def prepare(C: np.ndarray, A: float, strings: dict) -> dict:
    qubo = build_qubo(C, penalty=A)
    h, J, const = ising(qubo)
    scale = max(float(np.abs(h).max()), max((abs(v) for v in J.values()), default=0.0))
    energies = strings["cost"] + A * strings["V"]
    return {"qubo": qubo, "h": h, "J": J, "const": const, "scale": scale,
            "energies": energies, "diag": (energies - const) / scale}


def qaoa_circuit(h: np.ndarray, J: dict, scale: float, gammas, betas, measure: bool = False) -> QuantumCircuit:
    m = len(h)
    qc = QuantumCircuit(m)
    qc.h(range(m))
    for gamma, beta in zip(gammas, betas):
        for k in range(m):
            if h[k] != 0.0:
                qc.rz(2.0 * gamma * h[k] / scale, k)
        for (k, l), j in J.items():
            qc.rzz(2.0 * gamma * j / scale, k, l)
        for k in range(m):
            qc.rx(2.0 * beta, k)
    if measure:
        qc.measure_all()
    return qc


def simulate(diag: np.ndarray, m: int, gammas, betas) -> np.ndarray:
    psi = np.full(1 << m, 1.0 / math.sqrt(1 << m), dtype=complex)
    for gamma, beta in zip(gammas, betas):
        psi = psi * np.exp(-1j * gamma * diag)
        c, s = math.cos(beta), -1j * math.sin(beta)
        t = psi.reshape([2] * m)
        for axis in range(m):
            t0 = np.take(t, 0, axis=axis)
            t1 = np.take(t, 1, axis=axis)
            t = np.stack([c * t0 + s * t1, s * t0 + c * t1], axis=axis)
        psi = t.reshape(-1)
    return np.abs(psi) ** 2


def optimize(diag: np.ndarray, m: int, p: int, rng: np.random.Generator, starts: int, warm=None) -> tuple[np.ndarray, float]:
    def objective(v):
        return float(simulate(diag, m, v[:p], v[p:]) @ diag)

    initial = [np.concatenate([rng.uniform(0, math.pi, p), rng.uniform(0, math.pi / 2, p)]) for _ in range(starts)]
    if warm is not None:
        initial.insert(0, warm)
    best = None
    for x0 in initial:
        res = minimize(objective, x0, method="COBYLA", options={"maxiter": 300, "rhobeg": 0.3})
        if best is None or res.fun < best.fun:
            best = res
    return np.asarray(best.x), float(best.fun)


def interpolate(params: np.ndarray, p_prev: int, p: int) -> np.ndarray:
    old = np.linspace(0.0, 1.0, p_prev) if p_prev > 1 else np.array([0.0])
    new = np.linspace(0.0, 1.0, p)
    gammas = np.interp(new, old, params[:p_prev]) if p_prev > 1 else np.full(p, params[0])
    betas = np.interp(new, old, params[p_prev:]) if p_prev > 1 else np.full(p, params[1])
    return np.concatenate([gammas, betas])


def evaluate(probs: np.ndarray, strings: dict, optimum: float, shots: int, rng: np.random.Generator) -> dict:
    feasible = strings["V"] == 0
    optimal = feasible & (np.abs(strings["cost"] - optimum) <= 1e-6 * max(1.0, abs(optimum)))
    samples = rng.choice(len(probs), size=shots, p=probs / probs.sum())
    sample_feasible = feasible[samples]
    best_ratio = None
    if sample_feasible.any() and optimum > 0:
        best_ratio = float(strings["cost"][samples][sample_feasible].min() / optimum)
    return {
        "p_optimal": float(probs[optimal].sum()),
        "p_feasible": float(probs[feasible].sum()),
        "uniform_p_optimal": float(optimal.mean()),
        "uniform_p_feasible": float(feasible.mean()),
        "samples_found_optimum": bool(optimal[samples].any()),
        "best_sample_ratio": best_ratio,
    }


_HEAVY_HEX = None


def heavy_hex_backend():
    global _HEAVY_HEX
    if _HEAVY_HEX is None:
        from qiskit.providers.fake_provider import GenericBackendV2
        from qiskit.transpiler import CouplingMap

        coupling = CouplingMap.from_heavy_hex(3)
        _HEAVY_HEX = GenericBackendV2(num_qubits=coupling.size(), basis_gates=["cz", "rz", "sx", "x", "id"],
                                      coupling_map=coupling, seed=1)
    return _HEAVY_HEX


def resources(prep: dict, params: np.ndarray, p: int) -> dict:
    qc = qaoa_circuit(prep["h"], prep["J"], prep["scale"], params[:p], params[p:], measure=True)
    compiled = transpile(qc, backend=heavy_hex_backend(), optimization_level=3, seed_transpiler=7)
    ops = compiled.count_ops()
    return {"qubits": len(prep["h"]), "zz_terms": len(prep["J"]), "logical_depth": qc.depth(),
            "transpiled_depth": compiled.depth(), "two_qubit_gates": int(ops.get("cz", 0))}


def run(matrices: list, label: str, starts: int, shots: int, rng: np.random.Generator) -> dict:
    rows = []
    resource_rows = {}
    for index, C in enumerate(matrices):
        optimum = hungarian_cost(C)
        strings = enumerate_strings(C)
        a_crit = critical_penalty(strings, optimum)
        penalties = {"max_abs": max_abs_rule(C)}
        if a_crit > 0:
            penalties["oracle_1.5x_crit"] = 1.5 * a_crit
        record = {"index": index, "optimum": optimum, "A_crit": a_crit}
        for rule, A in penalties.items():
            prep = prepare(C, A, strings)
            check = ising_energies(prep["h"], prep["J"], prep["const"], strings["X"])
            if not np.allclose(check, prep["energies"], atol=1e-8 * max(1.0, prep["scale"])):
                raise SystemExit("Ising conversion does not reproduce the QUBO energies - stop")
            m = len(prep["h"])
            per_depth = {}
            warm = None
            for p in DEPTHS:
                params, expectation = optimize(prep["diag"], m, p, rng, starts, warm)
                probs = simulate(prep["diag"], m, params[:p], params[p:])
                result = evaluate(probs, strings, optimum, shots, rng)
                result.update({"expectation_scaled": expectation, "gammas": params[:p].tolist(), "betas": params[p:].tolist()})
                per_depth["p%d" % p] = result
                if index == 0 and rule == "max_abs":
                    resource_rows["p%d" % p] = resources(prep, params, p)
                warm = interpolate(params, p, p + 1)
            record[rule] = {"A": A, **per_depth}
        rows.append(record)

    summary = {"instances": len(rows), "resources_heavy_hex_estimate": resource_rows, "by_rule": {}}
    for rule in ("max_abs", "oracle_1.5x_crit"):
        present = [r for r in rows if rule in r]
        if not present:
            continue
        by_depth = {}
        for p in DEPTHS:
            key = "p%d" % p
            p_opt = np.array([r[rule][key]["p_optimal"] for r in present])
            p_feas = np.array([r[rule][key]["p_feasible"] for r in present])
            ratios = [r[rule][key]["best_sample_ratio"] for r in present if r[rule][key]["best_sample_ratio"] is not None]
            by_depth[key] = {
                "p_optimal_mean": float(p_opt.mean()),
                "p_optimal_sem": float(p_opt.std(ddof=1) / math.sqrt(len(p_opt))) if len(p_opt) > 1 else 0.0,
                "p_feasible_mean": float(p_feas.mean()),
                "p_feasible_sem": float(p_feas.std(ddof=1) / math.sqrt(len(p_feas))) if len(p_feas) > 1 else 0.0,
                "share_instances_optimum_in_samples": float(np.mean([r[rule][key]["samples_found_optimum"] for r in present])),
                "mean_best_sample_ratio": float(np.mean(ratios)) if ratios else None,
            }
        summary["by_rule"][rule] = {
            "instances": len(present),
            "uniform_p_optimal_mean": float(np.mean([r[rule]["p1"]["uniform_p_optimal"] for r in present])),
            "uniform_p_feasible": float(present[0][rule]["p1"]["uniform_p_feasible"]),
            "by_depth": by_depth,
        }
    summary["instances_detail"] = rows

    print("== %s: %d instances ==" % (label, len(rows)))
    for p, res in resource_rows.items():
        print("   resources %s: %d qubits, %d ZZ terms, logical depth %d -> heavy-hex depth %d, %d CZ"
              % (p, res["qubits"], res["zz_terms"], res["logical_depth"], res["transpiled_depth"], res["two_qubit_gates"]))
    for rule, s in summary["by_rule"].items():
        print("   rule %s (%d instances): uniform P(opt) %.4f, uniform P(feasible) %.4f"
              % (rule, s["instances"], s["uniform_p_optimal_mean"], s["uniform_p_feasible"]))
        for key, d in s["by_depth"].items():
            print("      %s  P(opt) %.4f +- %.4f   P(feasible) %.4f +- %.4f   optimum in %d shots: %.2f   best/opt %s"
                  % (key, d["p_optimal_mean"], d["p_optimal_sem"], d["p_feasible_mean"], d["p_feasible_sem"], shots,
                     d["share_instances_optimum_in_samples"],
                     "-" if d["mean_best_sample_ratio"] is None else "%.4f" % d["mean_best_sample_ratio"]))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", type=int, default=50)
    parser.add_argument("--starts", type=int, default=6)
    parser.add_argument("--shots", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=14)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    pure = dataclasses.replace(Params(), p_detect=1.0, clutter_per_scan=0.0, gate=None)
    two = [pure_cost(generate(2, pure, rng)) for _ in range(args.instances)]
    three = p1_2_instances()["pure 3x3"][: args.instances]

    results = {
        "pure 2x2": run(two, "pure 2x2 (4 qubits)", args.starts, args.shots, rng),
        "pure 3x3": run(three, "pure 3x3 (9 qubits, P1.2/P1.3 instances)", args.starts, args.shots, rng),
    }

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p1_4-qaoa-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    out.write_text(json.dumps({
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P1.4 QAOA on a simulator",
        "seed": args.seed,
        "starts": args.starts,
        "shots": args.shots,
        "depths": DEPTHS,
        "objective": "minimise <H> with COBYLA, maxiter 300, rhobeg 0.3; extra start interpolated from depth p-1",
        "resources_note": "heavy-hex (distance 3) CZ model via GenericBackendV2, optimization_level 3 - an estimate, not a real device",
        "results": results,
    }, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
