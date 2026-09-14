# P1.5 - QAOA for small assignment QUBOs on real IBM Quantum hardware.
#
# Nothing is optimised on hardware. Parameters come from the P1.4 simulator run (A = max|c|), and the instances are
# rebuilt exactly; before anything is submitted, the simulator is re-run with the stored parameters and must reproduce
# the stored P(optimal) to 1e-9, otherwise the script stops.
#
# Pre-registered selection (no cherry-picking): the FIRST 10 pure 2x2 instances at p = 1 and p = 2, and the FIRST 5 pure
# 3x3 instances at p = 1.
#
# Device: among ibm_kingston, ibm_fez and ibm_marrakesh, the one with the lowest median CZ error in today's calibration
# data (reading calibration data costs no QPU time). Transpiled with optimisation level 3 on that device.
#
# Readout: tensored (per-qubit) correction. For each size, two calibration circuits prepare all-0 and all-1 on the union
# of physical qubits the QAOA circuits are measured on. Each qubit gets a 2x2 assignment matrix; its inverse is applied
# along that qubit's axis of the probability tensor, then negatives are clipped and the vector renormalised. This assumes
# readout errors are independent between qubits (P0.5 measured the full matrix on 3 qubits; at 9 qubits that would take
# 512 circuits).
#
# Everything goes into ONE job, 2048 shots per circuit, so all results share one queue wait and one calibration window.
#
# Usage:
#     python src/p1_5_hardware.py --dry-run          # rank devices, transpile, print resources - submits nothing
#     python src/p1_5_hardware.py                    # submit and wait
#     python src/p1_5_hardware.py --collect results/p1_5-hardware-XXXX-submitted.json

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import pathlib

import numpy as np
from qiskit import QuantumCircuit, transpile

from p0_5_readout import measured_physical_qubits
from p1_annealing import p1_2_instances
from p1_penalty import enumerate_strings
from p1_qaoa import prepare, qaoa_circuit, simulate
from p1_qubo import hungarian_cost
from p1_scenario import RESULTS, Params, generate, pure_cost

P1_4_FILE = RESULTS / "p1_4-qaoa-20260914-131628.json"
PLAN = [("pure 2x2", [1, 2], 10), ("pure 3x3", [1], 5)]
DEVICES = ["ibm_kingston", "ibm_fez", "ibm_marrakesh"]


def rebuild_p1_4_instances() -> dict:
    """Same generation order as P1.4: 50 pure 2x2 from seed 14 first, and the P1.2 pure 3x3 set."""
    rng = np.random.default_rng(14)
    pure = dataclasses.replace(Params(), p_detect=1.0, clutter_per_scan=0.0, gate=None)
    two = [pure_cost(generate(2, pure, rng)) for _ in range(50)]
    return {"pure 2x2": two, "pure 3x3": p1_2_instances()["pure 3x3"][:50]}


def distribution_metrics(probs: np.ndarray, strings: dict, optimum: float) -> dict:
    feasible = strings["V"] == 0
    optimal = feasible & (np.abs(strings["cost"] - optimum) <= 1e-6 * max(1.0, abs(optimum)))
    return {"p_optimal": float(probs[optimal].sum()), "p_feasible": float(probs[feasible].sum())}


def planned_items(stored: dict, instances: dict) -> list:
    items = []
    for size, depths, count in PLAN:
        detail = stored["results"][size]["instances_detail"]
        for index in range(count):
            C = instances[size][index]
            record = detail[index]
            if abs(hungarian_cost(C) - record["optimum"]) > 1e-9:
                raise SystemExit("rebuilt %s instance %d does not match P1.4 - stop" % (size, index))
            strings = enumerate_strings(C)
            A = record["max_abs"]["A"]
            prep = prepare(C, A, strings)
            m = len(prep["h"])
            for p in depths:
                stored_depth = record["max_abs"]["p%d" % p]
                gammas, betas = stored_depth["gammas"], stored_depth["betas"]
                simulated = distribution_metrics(simulate(prep["diag"], m, gammas, betas), strings, record["optimum"])
                if abs(simulated["p_optimal"] - stored_depth["p_optimal"]) > 1e-9:
                    raise SystemExit("stored parameters do not reproduce P1.4 for %s instance %d p=%d - stop" % (size, index, p))
                items.append({
                    "size": size, "index": index, "p": p, "qubits": m, "A": A, "optimum": record["optimum"],
                    "gammas": gammas, "betas": betas, "simulator": simulated,
                    "circuit": qaoa_circuit(prep["h"], prep["J"], prep["scale"], gammas, betas, measure=True),
                })
    return items


def rank_devices(service) -> list:
    rows = []
    for name in DEVICES:
        target = service.backend(name).target
        cz = [props.error for props in target["cz"].values() if props is not None and props.error is not None] \
            if "cz" in target.operation_names else []
        readout = [props.error for props in target["measure"].values() if props is not None and props.error is not None]
        rows.append({"backend": name,
                     "median_cz_error": float(np.median(cz)) if cz else None,
                     "median_readout_error": float(np.median(readout)) if readout else None})
    rows.sort(key=lambda r: (r["median_cz_error"] is None, r["median_cz_error"] or 0.0))
    return rows


def calibration_pair(union: list, backend) -> list:
    k = len(union)
    zero = QuantumCircuit(k, k, name="cal_all0")
    zero.measure(range(k), range(k))
    one = QuantumCircuit(k, k, name="cal_all1")
    one.x(range(k))
    one.measure(range(k), range(k))
    compiled = [transpile(c, backend=backend, initial_layout=union, optimization_level=0) for c in (zero, one)]
    for c in compiled:
        if measured_physical_qubits(c) != union:
            raise SystemExit("calibration circuit is not measured on the intended qubits - stop")
    return compiled


def per_qubit_errors(counts_all0: dict, counts_all1: dict, union: list) -> dict:
    """p10[q] = P(read 1 | prepared 0), p01[q] = P(read 0 | prepared 1), keyed by physical qubit."""
    shots0, shots1 = sum(counts_all0.values()), sum(counts_all1.values())
    errors = {}
    for k, q in enumerate(union):
        read1_from0 = sum(c for bits, c in counts_all0.items() if bits[-1 - k] == "1") / shots0
        read0_from1 = sum(c for bits, c in counts_all1.items() if bits[-1 - k] == "0") / shots1
        errors[q] = (read1_from0, read0_from1)
    return errors


def tensored_correct(probs: np.ndarray, measured: list, errors: dict) -> np.ndarray:
    m = len(measured)
    t = probs.reshape([2] * m)
    for k, q in enumerate(measured):
        p10, p01 = errors[q]
        inverse = np.linalg.inv(np.array([[1 - p10, p01], [p10, 1 - p01]]))
        axis = m - 1 - k
        moved = np.moveaxis(t, axis, 0)
        t = np.moveaxis(np.tensordot(inverse, moved, axes=([1], [0])), 0, axis)
    v = np.clip(t.reshape(-1), 0, None)
    return v / v.sum()


def counts_to_probs(counts: dict, m: int) -> np.ndarray:
    probs = np.zeros(1 << m)
    total = sum(counts.values())
    for bits, c in counts.items():
        probs[int(bits, 2)] += c / total
    return probs


def submit(args) -> pathlib.Path:
    from qiskit.transpiler import generate_preset_pass_manager
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    stored = json.loads(P1_4_FILE.read_text(encoding="utf-8"))
    items = planned_items(stored, rebuild_p1_4_instances())
    print("fingerprint check passed: %d circuits reproduce P1.4 exactly" % len(items))

    service = QiskitRuntimeService()
    ranking = rank_devices(service)
    for r in ranking:
        print("  %-14s median CZ error %s   median readout error %s"
              % (r["backend"], "-" if r["median_cz_error"] is None else "%.4f" % r["median_cz_error"],
                 "-" if r["median_readout_error"] is None else "%.4f" % r["median_readout_error"]))
    backend = service.backend(args.backend or ranking[0]["backend"])
    print("device: %s" % backend.name)

    pass_manager = generate_preset_pass_manager(optimization_level=3, backend=backend, seed_transpiler=7)
    pubs, calibrations = [], {}
    for item in items:
        compiled = pass_manager.run(item["circuit"])
        ops = compiled.count_ops()
        item.update({"measured_physical_qubits": measured_physical_qubits(compiled),
                     "two_qubit_gates": int(ops.get("cz", 0)), "depth": compiled.depth(), "pub": len(pubs)})
        pubs.append(compiled)
        print("  %s #%d p=%d: %d CZ, depth %d, qubits %s"
              % (item["size"], item["index"], item["p"], item["two_qubit_gates"], item["depth"], item["measured_physical_qubits"]))
    for size, _, _ in PLAN:
        union = sorted({q for it in items if it["size"] == size for q in it["measured_physical_qubits"]})
        pair = calibration_pair(union, backend)
        calibrations[size] = {"union": union, "pub_all0": len(pubs), "pub_all1": len(pubs) + 1}
        pubs.extend(pair)
    total_shots = len(pubs) * args.shots
    print("%d circuits x %d shots = %d shots" % (len(pubs), args.shots, total_shots))

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    record = {
        "stamp": stamp, "experiment": "P1.5 QAOA on hardware", "status": "dry-run" if args.dry_run else "submitted",
        "backend": backend.name, "device_ranking": ranking, "shots": args.shots, "total_shots": total_shots,
        "penalty_rule": "A = max|c|", "readout": "tensored per-qubit correction",
        "items": [{k: v for k, v in it.items() if k != "circuit"} for it in items],
        "calibrations": calibrations,
    }
    if args.dry_run:
        print("dry run - nothing submitted")
        return None

    job = SamplerV2(mode=backend).run(pubs, shots=args.shots)
    record["job_id"] = job.job_id()
    record["submitted_at"] = dt.datetime.now().astimezone().isoformat()
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / ("p1_5-hardware-" + stamp + "-submitted.json")
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("submitted job %s to %s - saved %s" % (job.job_id(), backend.name, path))
    return path


def collect(path: pathlib.Path) -> None:
    from qiskit_ibm_runtime import QiskitRuntimeService

    record = json.loads(path.read_text(encoding="utf-8"))
    result = QiskitRuntimeService().job(record["job_id"]).result()
    instances = rebuild_p1_4_instances()

    errors = {}
    for size, cal in record["calibrations"].items():
        c0 = result[cal["pub_all0"]].data.c.get_counts()
        c1 = result[cal["pub_all1"]].data.c.get_counts()
        errors[size] = per_qubit_errors(c0, c1, cal["union"])
        cal["per_qubit_errors"] = {str(q): list(v) for q, v in errors[size].items()}

    for item in record["items"]:
        C = instances[item["size"]][item["index"]]
        strings = enumerate_strings(C)
        counts = result[item["pub"]].data.meas.get_counts()
        raw = counts_to_probs(counts, item["qubits"])
        corrected = tensored_correct(raw, item["measured_physical_qubits"], errors[item["size"]])
        item["hardware_raw"] = distribution_metrics(raw, strings, item["optimum"])
        item["hardware_corrected"] = distribution_metrics(corrected, strings, item["optimum"])
        item["counts"] = counts

    summary = {}
    for size, depths, _ in PLAN:
        for p in depths:
            chosen = [it for it in record["items"] if it["size"] == size and it["p"] == p]
            def mean(path_a, path_b):
                return float(np.mean([it[path_a][path_b] for it in chosen]))
            row = {
                "instances": len(chosen),
                "two_qubit_gates_mean": float(np.mean([it["two_qubit_gates"] for it in chosen])),
                "depth_mean": float(np.mean([it["depth"] for it in chosen])),
                "guess_p_optimal": 1 / (1 << chosen[0]["qubits"]) * (1 if size == "pure 2x2" else 1),
                "simulator_p_optimal": mean("simulator", "p_optimal"),
                "hardware_raw_p_optimal": mean("hardware_raw", "p_optimal"),
                "hardware_corrected_p_optimal": mean("hardware_corrected", "p_optimal"),
                "simulator_p_feasible": mean("simulator", "p_feasible"),
                "hardware_raw_p_feasible": mean("hardware_raw", "p_feasible"),
                "hardware_corrected_p_feasible": mean("hardware_corrected", "p_feasible"),
            }
            summary["%s p%d" % (size, p)] = row
            print("== %s p=%d: %d instances, %.0f CZ, depth %.0f ==" % (size, p, row["instances"], row["two_qubit_gates_mean"], row["depth_mean"]))
            print("   P(optimal)  simulator %.4f   hardware raw %.4f   corrected %.4f"
                  % (row["simulator_p_optimal"], row["hardware_raw_p_optimal"], row["hardware_corrected_p_optimal"]))
            print("   P(feasible) simulator %.4f   hardware raw %.4f   corrected %.4f"
                  % (row["simulator_p_feasible"], row["hardware_raw_p_feasible"], row["hardware_corrected_p_feasible"]))

    record["status"] = "done"
    record["finished_at"] = dt.datetime.now().astimezone().isoformat()
    record["summary"] = summary
    out = RESULTS / ("p1_5-hardware-" + record["stamp"] + ".json")
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots", type=int, default=2048)
    parser.add_argument("--backend", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--collect", type=str, default=None)
    args = parser.parse_args()
    if args.collect:
        collect(pathlib.Path(args.collect))
        return
    path = submit(args)
    if path is not None:
        collect(path)


if __name__ == "__main__":
    main()
