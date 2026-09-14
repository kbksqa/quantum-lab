# P3.2 cross-check against the QANTIS public repository, run with a SEPARATE Python environment that has qiskit-optimization
# (not needed by this project) and a clone of https://github.com/neuraparse/qantis. Nothing from the repository is copied here;
# its modules are imported from the clone at run time.
#
# Checks:
#   1. to_ising variable -> qubit mapping: the diagonal of the Ising operator the repository's solver builds is compared with
#      our QUBO energies, read with qubit k = bit k of the basis index and with the reversed order
#   2. QAOAAnsatz parameter order in this Qiskit version
#   3. what the repository's FPCQAOASolver returns on the instance at p = 1, 2, 3 (its own simulator path, 4096 shots,
#      COBYLA maxiter 100, as the hardware script calls it)
#
# Usage (from the quantum-lab repository root):
#     <env>/python tools/p3_repo_crosscheck.py --qantis-repo <clone> --out results/p3_2-repo-crosscheck.json

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import pathlib
import subprocess
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qantis-repo", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    repo = pathlib.Path(args.qantis_repo)
    sys.path.insert(0, str(repo / "packages" / "quantum-mht" / "src"))

    import qiskit
    import qiskit_optimization
    from qiskit.circuit.library import QAOAAnsatz
    from qiskit_optimization import QuadraticProgram
    from qiskit_optimization.translators import to_ising
    from quantum_mht.formulation.mtda_qubo_builder import MTDAQuboBuilder

    from p3_qantis_instance import COVARIANCE, N_MEAS, N_TRACKS, SEED, all_strings, build_qubo, cost_matrix, energy, generate

    rng = np.random.default_rng(SEED)
    predicted = rng.standard_normal((N_TRACKS, 2))
    measurements = rng.standard_normal((N_MEAS, 2))
    covariances = np.stack([np.eye(2) * COVARIANCE] * N_TRACKS)
    theirs = MTDAQuboBuilder().build(predicted, measurements, covariances)
    n = theirs.num_variables

    C, mask, _ = cost_matrix(generate(), "code")
    ours = build_qubo(C, mask)
    E = energy(ours, all_strings(n))

    qp = QuadraticProgram()
    for i in range(n):
        qp.binary_var("x%d" % i)
    linear, quadratic = {}, {}
    for (i, j), v in theirs.Q.items():
        if i == j:
            linear["x%d" % i] = linear.get("x%d" % i, 0.0) + v
        else:
            quadratic[("x%d" % i, "x%d" % j)] = quadratic.get(("x%d" % i, "x%d" % j), 0.0) + v
    qp.minimize(linear=linear, quadratic=quadratic)
    op, offset = to_ising(qp)

    idx = np.arange(1 << n)
    diag = np.full(1 << n, float(offset))
    for label, coeff in zip(op.paulis.to_labels(), op.coeffs):
        sign = np.ones(1 << n)
        for q in range(n):
            if label[n - 1 - q] == "Z":
                sign *= 1 - 2 * ((idx >> q) & 1)
        diag += float(np.real(coeff)) * sign
    rev = np.array([int(format(k, "0%db" % n)[::-1], 2) for k in range(1 << n)])
    mapping = {"max_abs_diff_identity": float(np.max(np.abs(diag - E))),
               "max_abs_diff_reversed": float(np.max(np.abs(diag - E[rev])))}
    mapping["variable_i_is_qubit_i"] = mapping["max_abs_diff_identity"] < 1e-8
    print("to_ising mapping:", mapping)

    order = [str(p) for p in QAOAAnsatz(op, reps=3).parameters]
    print("QAOAAnsatz parameter order:", order)

    fpc = load("qantis_fpc", repo / "packages" / "quantum-mht" / "src" / "quantum_mht" / "solvers" / "fpc_qaoa_solver.py")
    hung = load("qantis_hungarian", repo / "packages" / "quantum-mht" / "src" / "quantum_mht" / "solvers" /
                "classical_solvers" / "hungarian_solver.py").HungarianSolver().solve(theirs)
    runs = []
    for p in (1, 2, 3):
        start = time.perf_counter()
        result = fpc.FPCQAOASolver(depth=p, num_schedule_params=3, shots=4096, optimizer_maxiter=100).solve(theirs)
        row = {"p": p, "objective": float(result.objective_value),
               "ratio_to_hungarian": float(result.objective_value / abs(hung.objective_value)),
               "optimal_params": result.metadata.get("optimal_params"), "seconds": time.perf_counter() - start}
        runs.append(row)
        print("repository FPCQAOASolver p=%d: objective %.4f ratio %.4f (%.1f s)" % (p, row["objective"], row["ratio_to_hungarian"], row["seconds"]))

    record = {
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P3.2 cross-check against the QANTIS public repository",
        "repository_commit": subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "environment": {"python": sys.version.split()[0], "qiskit": qiskit.__version__, "qiskit_optimization": qiskit_optimization.__version__},
        "hungarian": float(hung.objective_value), "to_ising_mapping": mapping, "qaoa_ansatz_parameter_order": order,
        "repository_solver_runs": runs,
        "note": "The repository solver samples with StatevectorSampler without a fixed seed, so its objective can vary run to run.",
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
