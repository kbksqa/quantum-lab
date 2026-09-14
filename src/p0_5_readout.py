# P0.5 - How much of the hardware loss is readout error?
#
# Hypothesis from P0: on ibm_kingston, wrong outcomes favoured states one bit away from the marked
# state. If that came mainly from readout (measurement) errors, correcting the readout should remove
# most of the bias. If the bias survives the correction, it came from the gates.
#
# Method, per device:
#   1. Transpile Grover (k = 2) for the device and find which physical qubit feeds each classical bit.
#   2. On exactly those physical qubits, prepare each basis state |s> and measure it at once.
#      This gives the assignment matrix A[j][s] = P(read j | prepared s).
#   3. Correct the Grover distribution: solve A p = p_measured, clip negatives, renormalise.
#   4. Compare raw and corrected success rate and error anatomy (by Hamming distance).
# Grover and calibration circuits go into ONE job per device, so they share a calibration window.
#
# Usage:
#     python src/p0_5_readout.py --simulate-readout-error 0.03       # validate the method, no hardware
#     python src/p0_5_readout.py                                     # submit to three devices and wait
#     python src/p0_5_readout.py --collect results/p0_5-readout-XXXX-submitted.json

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib

import numpy as np
from qiskit import QuantumCircuit, transpile

from p0_grover import RESULTS, grover_circuit

TWO_QUBIT_GATES = {"cz", "ecr", "cx", "rzz"}


def calibration_circuits(n: int) -> list[QuantumCircuit]:
    """Prepare every basis state |s> (bit i of s on qubit i) and measure it immediately."""
    circuits = []
    for s in range(2 ** n):
        qc = QuantumCircuit(n, n, name="cal_%s" % format(s, "0%db" % n))
        for i in range(n):
            if (s >> i) & 1:
                qc.x(i)
        qc.measure(range(n), range(n))
        circuits.append(qc)
    return circuits


def measured_physical_qubits(circuit: QuantumCircuit) -> list[int]:
    """Physical qubit index measured into classical bit 0, 1, 2, ..."""
    mapping = {}
    for instruction in circuit.data:
        if instruction.operation.name == "measure":
            qubit = circuit.find_bit(instruction.qubits[0]).index
            clbit = circuit.find_bit(instruction.clbits[0]).index
            mapping[clbit] = qubit
    return [mapping[c] for c in sorted(mapping)]


def to_probabilities(counts: dict, n: int) -> np.ndarray:
    vector = np.zeros(2 ** n)
    total = sum(counts.values())
    for bits, c in counts.items():
        vector[int(bits, 2)] += c / total
    return vector


def assignment_matrix(calibration_counts: list[dict], n: int) -> np.ndarray:
    """Column s = distribution measured after preparing |s>."""
    return np.column_stack([to_probabilities(c, n) for c in calibration_counts])


def correct(A: np.ndarray, p_measured: np.ndarray) -> np.ndarray:
    p = np.linalg.solve(A, p_measured)
    p = np.clip(p, 0, None)
    return p / p.sum()


def anatomy(p: np.ndarray, marked: str, n: int) -> list[dict]:
    target = int(marked, 2)
    rows = []
    for distance in range(n + 1):
        states = [s for s in range(2 ** n) if bin(s ^ target).count("1") == distance]
        share = float(sum(p[s] for s in states))
        rows.append({"hamming_distance": distance, "states": len(states),
                     "probability": share, "probability_per_state": share / len(states)})
    return rows


def qubit_readout_errors(A: np.ndarray, n: int) -> list[dict]:
    """Per classical bit: P(read 1 | prepared 0) and P(read 0 | prepared 1), averaged over the others."""
    out = []
    for i in range(n):
        p01, p10, count0, count1 = 0.0, 0.0, 0, 0
        for s in range(2 ** n):
            read_one = sum(A[j, s] for j in range(2 ** n) if (j >> i) & 1)
            if (s >> i) & 1:
                p10 += 1 - read_one
                count1 += 1
            else:
                p01 += read_one
                count0 += 1
        out.append({"bit": i, "p_read1_given0": p01 / count0, "p_read0_given1": p10 / count1})
    return out


def analyse(grover_counts: dict, calibration_counts: list[dict], n: int, marked: str) -> dict:
    A = assignment_matrix(calibration_counts, n)
    raw = to_probabilities(grover_counts, n)
    corrected = correct(A, raw)
    target = int(marked, 2)
    return {
        "raw_success": float(raw[target]),
        "corrected_success": float(corrected[target]),
        "readout_errors": qubit_readout_errors(A, n),
        "assignment_matrix_diagonal": [float(A[s, s]) for s in range(2 ** n)],
        "anatomy_raw": anatomy(raw, marked, n),
        "anatomy_corrected": anatomy(corrected, marked, n),
    }


def print_report(label: str, res: dict, n: int) -> None:
    print("== %s ==" % label)
    print("success  raw %.4f  ->  readout-corrected %.4f" % (res["raw_success"], res["corrected_success"]))
    for q in res["readout_errors"]:
        print("  bit %d readout error: 0->1 %.4f   1->0 %.4f" % (q["bit"], q["p_read1_given0"], q["p_read0_given1"]))
    print("  per-state probability by distance from marked   raw    corrected")
    for r, c in zip(res["anatomy_raw"], res["anatomy_corrected"]):
        print("    distance %d                                  %.4f   %.4f"
              % (r["hamming_distance"], r["probability_per_state"], c["probability_per_state"]))


def simulate(args: argparse.Namespace) -> None:
    """Validate the method: ideal gates + known readout error. Correction must recover theory."""
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel, ReadoutError

    e = args.simulate_readout_error
    noise = NoiseModel()
    noise.add_all_qubit_readout_error(ReadoutError([[1 - e, e], [e, 1 - e]]))
    backend = AerSimulator(noise_model=noise)
    circuits = [grover_circuit(args.qubits, args.marked, args.iterations)] + calibration_circuits(args.qubits)
    result = backend.run(transpile(circuits, backend), shots=args.shots, seed_simulator=args.seed).result()
    counts = [result.get_counts(i) for i in range(len(circuits))]
    res = analyse(counts[0], counts[1:], args.qubits, args.marked)
    theta = math.asin(1 / math.sqrt(2 ** args.qubits))
    theory = math.sin((2 * args.iterations + 1) * theta) ** 2
    print_report("simulator with readout error %.3f (theory %.4f)" % (e, theory), res, args.qubits)
    print("recovered within %.4f of theory" % abs(res["corrected_success"] - theory))


def submit(args: argparse.Namespace) -> pathlib.Path:
    from qiskit.transpiler import generate_preset_pass_manager
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    service = QiskitRuntimeService()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    runs = []
    for name in args.backends:
        backend = service.backend(name)
        pass_manager = generate_preset_pass_manager(optimization_level=3, backend=backend)
        grover = pass_manager.run(grover_circuit(args.qubits, args.marked, args.iterations))
        physical = measured_physical_qubits(grover)
        calibration = [transpile(c, backend=backend, initial_layout=physical, optimization_level=1)
                       for c in calibration_circuits(args.qubits)]
        for c in calibration:
            if measured_physical_qubits(c) != physical:
                raise SystemExit("calibration landed on different qubits than Grover on " + name)
        ops = grover.count_ops()
        job = SamplerV2(mode=backend).run([grover] + calibration, shots=args.shots)
        print("submitted %s to %s (measured physical qubits %s)" % (job.job_id(), name, physical))
        runs.append({"backend": name, "job_id": job.job_id(), "measured_physical_qubits": physical,
                     "grover_depth": grover.depth(),
                     "grover_two_qubit_gates": int(sum(ops.get(g, 0) for g in TWO_QUBIT_GATES))})
    record = {"stamp": stamp, "experiment": "P0.5 readout error and correction", "status": "submitted",
              "qubits": args.qubits, "marked": args.marked, "iterations": args.iterations,
              "shots": args.shots, "runs": runs,
              "submitted_at": dt.datetime.now().astimezone().isoformat()}
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / ("p0_5-readout-" + stamp + "-submitted.json")
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(path))
    return path


def collect(path: pathlib.Path) -> None:
    from qiskit_ibm_runtime import QiskitRuntimeService

    service = QiskitRuntimeService()
    record = json.loads(path.read_text(encoding="utf-8"))
    n, marked = record["qubits"], record["marked"]
    for run in record["runs"]:
        result = service.job(run["job_id"]).result()
        counts = [result[i].data.c.get_counts() for i in range(1 + 2 ** n)]
        run.update(analyse(counts[0], counts[1:], n, marked))
        run["grover_counts"] = counts[0]
        print_report("%s  (2q gates %d, qubits %s)" % (run["backend"], run["grover_two_qubit_gates"],
                                                       run["measured_physical_qubits"]), run, n)
    record["status"] = "done"
    record["finished_at"] = dt.datetime.now().astimezone().isoformat()
    out = RESULTS / ("p0_5-readout-" + record["stamp"] + ".json")
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qubits", type=int, default=3)
    parser.add_argument("--marked", type=str, default="101")
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--backends", nargs="+", default=["ibm_kingston", "ibm_fez", "ibm_marrakesh"])
    parser.add_argument("--simulate-readout-error", type=float, default=None)
    parser.add_argument("--collect", type=str, default=None)
    args = parser.parse_args()

    if args.simulate_readout_error is not None:
        simulate(args)
    elif args.collect:
        collect(pathlib.Path(args.collect))
    else:
        collect(submit(args))


if __name__ == "__main__":
    main()
