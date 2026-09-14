# P0 - Grover iteration sweep on real IBM Quantum hardware.
#
# All iteration counts k = 0..K are submitted as ONE job, so there is one queue wait and the
# comparison is made on the same device calibration. For each k we record:
#   - the closed-form theory sin^2((2k+1)theta)
#   - the measured success rate on hardware
#   - the transpiled depth and number of two-qubit gates (the main driver of hardware error)
#
# The job id is written to results/ as soon as the job is submitted, so the run can always be
# recovered later with --job-id even if this process is interrupted while waiting in the queue.
#
# Usage:
#     python src/p0_hardware_sweep.py                       # least busy device
#     python src/p0_hardware_sweep.py --backend ibm_kingston
#     python src/p0_hardware_sweep.py --job-id <ID>         # collect results of an earlier job

from __future__ import annotations

import argparse
import datetime as dt
import json
import math

from p0_grover import RESULTS, grover_circuit, success_rate

TWO_QUBIT_GATES = {"cz", "ecr", "cx", "rzz"}


def theory(n_qubits: int, k: int, n_marked: int = 1) -> float:
    theta = math.asin(math.sqrt(n_marked / 2 ** n_qubits))
    return math.sin((2 * k + 1) * theta) ** 2


def save(record: dict, suffix: str) -> None:
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p0-hardware-sweep-" + record["stamp"] + suffix + ".json")
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qubits", type=int, default=3)
    parser.add_argument("--marked", type=str, default="101")
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--backend", type=str, default=None)
    parser.add_argument("--job-id", type=str, default=None)
    args = parser.parse_args()

    from qiskit.transpiler import generate_preset_pass_manager
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    service = QiskitRuntimeService()
    ks = list(range(args.max_iterations + 1))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")

    if args.job_id:
        job = service.job(args.job_id)
        backend_name = job.backend().name
        circuit_info = [{"iterations": k} for k in ks]
    else:
        backend = (
            service.backend(args.backend)
            if args.backend
            else service.least_busy(operational=True, simulator=False)
        )
        backend_name = backend.name
        pass_manager = generate_preset_pass_manager(optimization_level=3, backend=backend)

        isa_circuits = []
        circuit_info = []
        for k in ks:
            isa = pass_manager.run(grover_circuit(args.qubits, args.marked, k))
            ops = isa.count_ops()
            circuit_info.append(
                {
                    "iterations": k,
                    "transpiled_depth": isa.depth(),
                    "two_qubit_gates": int(sum(ops.get(g, 0) for g in TWO_QUBIT_GATES)),
                }
            )
            isa_circuits.append(isa)

        job = SamplerV2(mode=backend).run(isa_circuits, shots=args.shots)
        pending = {
            "stamp": stamp,
            "experiment": "P0 Grover iteration sweep - hardware",
            "status": "submitted",
            "backend": backend_name,
            "job_id": job.job_id(),
            "qubits": args.qubits,
            "marked": args.marked,
            "shots": args.shots,
            "circuits": circuit_info,
            "submitted_at": dt.datetime.now().astimezone().isoformat(),
        }
        print("submitted job " + job.job_id() + " to " + backend_name + " - waiting in the queue...")
        save(pending, "-submitted")

    result = job.result()

    rows = []
    print("k | depth | 2q gates | theory | hardware | diff")
    for i, k in enumerate(ks):
        counts = result[i].data.c.get_counts()
        p_hw = success_rate(counts, args.marked)
        p_th = theory(args.qubits, k)
        info = circuit_info[i]
        row = dict(info, theory=p_th, hardware=p_hw, diff=p_hw - p_th, counts=counts)
        rows.append(row)
        print(
            "%d | %5s | %8s | %.4f | %.4f   | %+.4f"
            % (k, info.get("transpiled_depth", "-"), info.get("two_qubit_gates", "-"), p_th, p_hw, p_hw - p_th)
        )

    usage_seconds = None
    try:
        usage_seconds = job.metrics().get("usage", {}).get("quantum_seconds")
    except Exception:
        pass

    record = {
        "stamp": stamp,
        "experiment": "P0 Grover iteration sweep - hardware",
        "status": "done",
        "backend": backend_name,
        "job_id": job.job_id(),
        "qubits": args.qubits,
        "marked": args.marked,
        "shots": args.shots,
        "quantum_seconds_used": usage_seconds,
        "uniform_baseline": 1 / 2 ** args.qubits,
        "rows": rows,
        "finished_at": dt.datetime.now().astimezone().isoformat(),
    }
    if usage_seconds is not None:
        print("QPU time used: %s s" % usage_seconds)
    save(record, "")


if __name__ == "__main__":
    main()
