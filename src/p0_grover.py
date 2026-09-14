# P0 - Grover search, built from primitive gates, run on a simulator and on real hardware.
#
# The point of this experiment is not speed (there is none at this size). It is to see, directly,
# how amplitude amplification behaves in theory and how far real hardware drifts away from it.
#
# Usage:
#     python src/p0_grover.py                  # simulator only
#     python src/p0_grover.py --hardware       # also submit to IBM Quantum

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib

from qiskit import QuantumCircuit, transpile

RESULTS = pathlib.Path(__file__).resolve().parents[1] / "results"


def oracle(n_qubits: int, marked: str) -> QuantumCircuit:
    """Flip the phase of one marked basis state, using only X, H and MCX."""
    qc = QuantumCircuit(n_qubits, name="oracle")
    for index, bit in enumerate(reversed(marked)):
        if bit == "0":
            qc.x(index)
    qc.h(n_qubits - 1)
    qc.mcx(list(range(n_qubits - 1)), n_qubits - 1)
    qc.h(n_qubits - 1)
    for index, bit in enumerate(reversed(marked)):
        if bit == "0":
            qc.x(index)
    return qc


def diffuser(n_qubits: int) -> QuantumCircuit:
    """Reflection about the uniform superposition."""
    qc = QuantumCircuit(n_qubits, name="diffuser")
    qc.h(range(n_qubits))
    qc.x(range(n_qubits))
    qc.h(n_qubits - 1)
    qc.mcx(list(range(n_qubits - 1)), n_qubits - 1)
    qc.h(n_qubits - 1)
    qc.x(range(n_qubits))
    qc.h(range(n_qubits))
    return qc


def grover_circuit(n_qubits: int, marked: str, iterations: int) -> QuantumCircuit:
    qc = QuantumCircuit(n_qubits, n_qubits)
    qc.h(range(n_qubits))
    for _ in range(iterations):
        qc.compose(oracle(n_qubits, marked), inplace=True)
        qc.compose(diffuser(n_qubits), inplace=True)
    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def optimal_iterations(n_qubits: int, n_marked: int = 1) -> int:
    """floor(pi/4 * sqrt(N/M)) - where the marked state peaks."""
    return int(math.floor(math.pi / 4 * math.sqrt(2 ** n_qubits / n_marked)))


def run_simulator(qc: QuantumCircuit, shots: int) -> dict:
    from qiskit_aer import AerSimulator

    backend = AerSimulator()
    return backend.run(transpile(qc, backend), shots=shots).result().get_counts()


def run_hardware(qc: QuantumCircuit, shots: int):
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    service = QiskitRuntimeService()
    backend = service.least_busy(operational=True, simulator=False)
    isa_circuit = transpile(qc, backend=backend, optimization_level=3)
    job = SamplerV2(mode=backend).run([isa_circuit], shots=shots)
    print("submitted job " + job.job_id() + " to " + backend.name + " - this can take a while")
    return job.result()[0].data.c.get_counts(), backend.name


def success_rate(counts: dict, marked: str) -> float:
    total = sum(counts.values())
    return counts.get(marked, 0) / total if total else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qubits", type=int, default=3)
    parser.add_argument("--marked", type=str, default="101")
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument("--hardware", action="store_true")
    args = parser.parse_args()

    if len(args.marked) != args.qubits:
        raise SystemExit("marked state does not match the number of qubits")

    iterations = args.iterations if args.iterations is not None else optimal_iterations(args.qubits)
    qc = grover_circuit(args.qubits, args.marked, iterations)

    print("Grover: qubits=%d marked=%s iterations=%d" % (args.qubits, args.marked, iterations))
    print("circuit depth=%d gates=%s" % (qc.depth(), qc.count_ops()))

    record = {
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "qubits": args.qubits,
        "marked": args.marked,
        "iterations": iterations,
        "shots": args.shots,
        "depth": qc.depth(),
    }

    sim_counts = run_simulator(qc, args.shots)
    record["simulator"] = {
        "counts": sim_counts,
        "success_rate": success_rate(sim_counts, args.marked),
    }
    print("simulator success rate : %.3f" % record["simulator"]["success_rate"])

    if args.hardware:
        hw_counts, backend_name = run_hardware(qc, args.shots)
        record["hardware"] = {
            "backend": backend_name,
            "counts": hw_counts,
            "success_rate": success_rate(hw_counts, args.marked),
        }
        print("hardware (%s) success rate : %.3f" % (backend_name, record["hardware"]["success_rate"]))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p0-grover-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
