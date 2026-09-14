# P0 - Grover iteration sweep: simulator vs closed-form theory.
#
# For N = 2^n states with M marked, after k Grover iterations the probability of measuring a
# marked state is sin^2((2k + 1) * theta), where sin(theta) = sqrt(M / N).
# This script runs k = 0..K on the simulator with a fixed seed, compares each point with the
# formula, and stores everything in results/ so the comparison can be reproduced exactly.
#
# Usage:
#     python src/p0_sweep.py
#     python src/p0_sweep.py --max-iterations 8 --seed 7

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib

from qiskit import transpile

from p0_grover import RESULTS, grover_circuit, success_rate


def theory(n_qubits: int, k: int, n_marked: int = 1) -> float:
    theta = math.asin(math.sqrt(n_marked / 2 ** n_qubits))
    return math.sin((2 * k + 1) * theta) ** 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qubits", type=int, default=3)
    parser.add_argument("--marked", type=str, default="101")
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args()

    from qiskit_aer import AerSimulator

    backend = AerSimulator()
    rows = []
    print("k | theory | simulator | diff    | sigma  | diff/sigma")
    for k in range(args.max_iterations + 1):
        qc = grover_circuit(args.qubits, args.marked, k)
        counts = backend.run(
            transpile(qc, backend), shots=args.shots, seed_simulator=args.seed
        ).result().get_counts()
        p_theory = theory(args.qubits, k)
        p_sim = success_rate(counts, args.marked)
        sigma = math.sqrt(p_theory * (1 - p_theory) / args.shots)
        z = (p_sim - p_theory) / sigma if sigma > 0 else 0.0
        rows.append(
            {
                "iterations": k,
                "depth": qc.depth(),
                "theory": p_theory,
                "simulator": p_sim,
                "diff": p_sim - p_theory,
                "shot_noise_sigma": sigma,
                "z": z,
            }
        )
        print("%d | %.4f | %.4f    | %+.4f | %.4f | %+.2f" % (k, p_theory, p_sim, p_sim - p_theory, sigma, z))

    record = {
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P0 Grover iteration sweep",
        "qubits": args.qubits,
        "marked": args.marked,
        "shots": args.shots,
        "seed": args.seed,
        "rows": rows,
        "max_abs_z": max(abs(r["z"]) for r in rows),
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p0-sweep-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("max |z| = %.2f" % record["max_abs_z"])
    print("saved " + str(out))


if __name__ == "__main__":
    main()
