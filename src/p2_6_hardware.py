# P2.6 - Hardware: (A) repeat of the P1.5 2x2 p = 2 circuits for H5, and (B) three-dimensional QAOA at depth 1.
#
# Nothing is optimised on hardware. Parameters come from the simulator runs (P1.4 for A, P2.5 for B, A = max|c|). Instances
# are rebuilt exactly, and the stored parameters must reproduce the stored simulator P(optimal) to 1e-9, or the script stops.
#
# (A) H5: the same 10 pure 2x2 instances at p = 2 as P1.5. By default on the best device other than ibm_kingston, the
#     P1.5 device.
# (B) 3D: the P2.5 "sparse T=2" set at p = 1, on today's best device. Selection rule, fixed before transpiling: the FIRST 10
#     instances, in P2.5 order, whose transpiled circuit on that device has at most 60 CZ gates (the P2.5 go rule).
#
# Device ranking: lowest median CZ error in today's calibration data (reading it costs no QPU time), among ibm_kingston,
# ibm_fez and ibm_marrakesh. Readout: tensored per-qubit correction with all-0 / all-1 calibration circuits on the union of
# measured qubits, as in P1.5. 2048 shots per circuit; one job per device.
#
# Usage:
#     python src/p2_6_hardware.py --dry-run                     # rank, rebuild, transpile, select - saves a plan, submits nothing
#     python src/p2_6_hardware.py --plan results/p2_6-plan-XXXX.json   # submit exactly that plan, then collect
#     python src/p2_6_hardware.py --collect results/p2_6-hardware-XXXX-submitted.json

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

import numpy as np

from p0_5_readout import measured_physical_qubits
from p1_5_hardware import (
    DEVICES,
    P1_4_FILE,
    calibration_pair,
    counts_to_probs,
    distribution_metrics,
    per_qubit_errors,
    planned_items,
    rank_devices,
    rebuild_p1_4_instances,
    tensored_correct,
)
from p1_penalty import enumerate_strings as p1_strings
from p1_qaoa import qaoa_circuit, simulate
from p2_ilp import solve_ilp
from p2_qaoa import enumerate_strings, prepare, pure_set, sparse_set
from p2_scene import RESULTS

P1_5_FILE = RESULTS / "p1_5-hardware-20260914-133130.json"
P2_5_FILE = RESULTS / "p2_5-qaoa-20260914-160839.json"
MAX_CZ = 60
SELECT_3D = 10
P1_5_DEVICE = "ibm_kingston"


def h5_items() -> list:
    stored = json.loads(P1_4_FILE.read_text(encoding="utf-8"))
    items = [it for it in planned_items(stored, rebuild_p1_4_instances()) if it["size"] == "pure 2x2" and it["p"] == 2]
    for it in items:
        it["experiment"] = "A"
    return items


def rebuild_sparse(stored: dict) -> list:
    """Same generation order as P2.5: the pure set first, then the sparse set, from the stored seed."""
    n = len(stored["sets"]["sparse T=2"]["instances_detail"])
    rng = np.random.default_rng(stored["seed"])
    pure_set(n, rng)
    return sparse_set(n, rng)[0]


def items_3d() -> list:
    stored = json.loads(P2_5_FILE.read_text(encoding="utf-8"))
    detail = stored["sets"]["sparse T=2"]["instances_detail"]
    items = []
    for index, ((scene, ts), record) in enumerate(zip(rebuild_sparse(stored), detail)):
        optimum = solve_ilp(scene, ts)["cost"]
        if abs(optimum - record["optimum"]) > 1e-9 or len(ts.tuples) != record["variables"]:
            raise SystemExit("rebuilt sparse instance %d does not match P2.5 - stop" % index)
        strings = enumerate_strings(scene, ts)
        rule = record["qaoa"]["max_abs"]
        prep = prepare(scene, ts, rule["A"], strings)
        gammas, betas = rule["p1"]["gammas"], rule["p1"]["betas"]
        simulated = distribution_metrics(simulate(prep["diag"], len(prep["h"]), gammas, betas), strings, optimum)
        if abs(simulated["p_optimal"] - rule["p1"]["p_optimal"]) > 1e-9:
            raise SystemExit("stored parameters do not reproduce P2.5 for sparse instance %d - stop" % index)
        items.append({"experiment": "B", "size": "sparse T=2", "index": index, "p": 1, "qubits": len(prep["h"]),
                      "A": rule["A"], "optimum": optimum, "gammas": gammas, "betas": betas, "simulator": simulated,
                      "uniform_p_optimal": record["uniform_p_optimal"],
                      "circuit": qaoa_circuit(prep["h"], prep["J"], prep["scale"], gammas, betas, measure=True)})
    return items


def compile_items(items: list, backend) -> None:
    from qiskit.transpiler import generate_preset_pass_manager

    pass_manager = generate_preset_pass_manager(optimization_level=3, backend=backend, seed_transpiler=7)
    for it in items:
        compiled = pass_manager.run(it["circuit"])
        it.update({"compiled": compiled, "two_qubit_gates": int(compiled.count_ops().get("cz", 0)),
                   "depth": compiled.depth(), "measured_physical_qubits": measured_physical_qubits(compiled)})


def build(service, devices: dict, selected_3d: list | None) -> dict:
    experiments = {}
    for name, items in (("A", h5_items()), ("B", items_3d())):
        backend = service.backend(devices[name])
        compile_items(items, backend)
        if name == "B":
            if selected_3d is None:
                selected_3d = [it["index"] for it in items if it["two_qubit_gates"] <= MAX_CZ][:SELECT_3D]
            items = [it for it in items if it["index"] in selected_3d]
        union = sorted({q for it in items for q in it["measured_physical_qubits"]})
        experiments[name] = {"backend": backend.name, "items": items, "union": union,
                             "calibration": calibration_pair(union, backend)}
    return experiments


def describe(experiments: dict) -> dict:
    out = {}
    for name, e in experiments.items():
        items = e["items"]
        out[name] = {
            "backend": e["backend"], "instances": [it["index"] for it in items], "union": e["union"],
            "circuits": len(items) + 2,
            "two_qubit_gates": [it["two_qubit_gates"] for it in items],
            "simulator_p_optimal_mean": float(np.mean([it["simulator"]["p_optimal"] for it in items])),
            "simulator_p_feasible_mean": float(np.mean([it["simulator"]["p_feasible"] for it in items])),
            "uniform_p_optimal_mean": float(np.mean([it["uniform_p_optimal"] for it in items])) if name == "B" else 1 / 16,
            "items": [{k: v for k, v in it.items() if k not in ("circuit", "compiled")} for it in items],
        }
    return out


def main_submit(args) -> pathlib.Path | None:
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    service = QiskitRuntimeService()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.plan:
        plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))
        devices = {name: plan["experiments"][name]["backend"] for name in ("A", "B")}
        selected = plan["experiments"]["B"]["instances"]
        ranking = plan["device_ranking"]
    else:
        ranking = rank_devices(service)
        for r in ranking:
            print("  %-14s median CZ error %.4f   median readout error %.4f"
                  % (r["backend"], r["median_cz_error"], r["median_readout_error"]))
        devices = {"A": args.h5_backend or next(r["backend"] for r in ranking if r["backend"] != P1_5_DEVICE),
                   "B": args.backend_3d or ranking[0]["backend"]}
        selected = None
    experiments = build(service, devices, selected)
    summary = describe(experiments)
    for name, s in summary.items():
        print("experiment %s on %s: instances %s, CZ %s, simulator P(opt) %.4f, uniform %.4f, %d circuits"
              % (name, s["backend"], s["instances"], s["two_qubit_gates"], s["simulator_p_optimal_mean"],
                 s["uniform_p_optimal_mean"], s["circuits"]))
    if args.plan:
        registered = plan["experiments"]
        for name in ("A", "B"):
            if summary[name]["two_qubit_gates"] != registered[name]["two_qubit_gates"]:
                print("note: experiment %s CZ counts changed since the plan: %s -> %s"
                      % (name, registered[name]["two_qubit_gates"], summary[name]["two_qubit_gates"]))
            if name == "B" and max(summary[name]["two_qubit_gates"]) > MAX_CZ:
                raise SystemExit("a registered 3D circuit now needs more than %d CZ - stop, re-plan" % MAX_CZ)
    total_shots = sum(s["circuits"] for s in summary.values()) * args.shots
    print("total %d shots" % total_shots)
    record = {"stamp": stamp, "experiment": "P2.6 hardware", "device_ranking": ranking, "shots": args.shots,
              "total_shots": total_shots, "experiments": summary, "max_cz_rule": MAX_CZ}

    if args.dry_run:
        path = RESULTS / ("p2_6-plan-%s.json" % stamp)
        record["status"] = "plan (dry run, nothing submitted)"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print("dry run - nothing submitted - plan saved " + str(path))
        return None

    record["plan_file"] = args.plan
    for name, e in experiments.items():
        pubs = [it["compiled"] for it in e["items"]] + e["calibration"]
        job = SamplerV2(mode=service.backend(e["backend"])).run(pubs, shots=args.shots)
        record["experiments"][name]["job_id"] = job.job_id()
        print("submitted experiment %s: job %s on %s" % (name, job.job_id(), e["backend"]))
    record["status"] = "submitted"
    record["submitted_at"] = dt.datetime.now().astimezone().isoformat()
    path = RESULTS / ("p2_6-hardware-%s-submitted.json" % stamp)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(path))
    return path


def collect(path: pathlib.Path, prefix: str = "p2_6-hardware") -> pathlib.Path:
    from qiskit_ibm_runtime import QiskitRuntimeService

    record = json.loads(path.read_text(encoding="utf-8"))
    service = QiskitRuntimeService()
    p14 = rebuild_p1_4_instances()
    sparse = rebuild_sparse(json.loads(P2_5_FILE.read_text(encoding="utf-8")))
    for name, e in record["experiments"].items():
        job = service.job(e["job_id"])
        result = job.result()
        n = len(e["items"])
        errors = per_qubit_errors(result[n].data.c.get_counts(), result[n + 1].data.c.get_counts(), e["union"])
        e["per_qubit_errors"] = {str(q): list(v) for q, v in errors.items()}
        for k, it in enumerate(e["items"]):
            if name == "A":
                strings = p1_strings(p14["pure 2x2"][it["index"]])
            else:
                strings = enumerate_strings(*sparse[it["index"]])
            counts = result[k].data.meas.get_counts()
            raw = counts_to_probs(counts, it["qubits"])
            corrected = tensored_correct(raw, it["measured_physical_qubits"], errors)
            it["hardware_raw"] = distribution_metrics(raw, strings, it["optimum"])
            it["hardware_corrected"] = distribution_metrics(corrected, strings, it["optimum"])
            it["counts"] = counts
        try:
            e["usage_seconds"] = job.usage()
        except Exception as exc:  # noqa: BLE001 - usage reporting is optional
            e["usage_seconds"] = "unavailable: %s" % exc
        mean = lambda key, field: float(np.mean([it[key][field] for it in e["items"]]))  # noqa: E731
        e["summary"] = {
            "simulator_p_optimal": mean("simulator", "p_optimal"),
            "hardware_raw_p_optimal": mean("hardware_raw", "p_optimal"),
            "hardware_corrected_p_optimal": mean("hardware_corrected", "p_optimal"),
            "simulator_p_feasible": mean("simulator", "p_feasible"),
            "hardware_corrected_p_feasible": mean("hardware_corrected", "p_feasible"),
            "retention_corrected": mean("hardware_corrected", "p_optimal") / mean("simulator", "p_optimal"),
            "retention_raw": mean("hardware_raw", "p_optimal") / mean("simulator", "p_optimal"),
            "ratio_to_guessing_corrected": mean("hardware_corrected", "p_optimal") / e["uniform_p_optimal_mean"],
        }
        print("== experiment %s on %s: %s" % (name, e["backend"], {k: round(v, 4) for k, v in e["summary"].items()}))
    record["status"] = "done"
    record["finished_at"] = dt.datetime.now().astimezone().isoformat()
    out = RESULTS / ("%s-%s.json" % (prefix, record["stamp"]))
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots", type=int, default=2048)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan", type=str, default=None)
    parser.add_argument("--h5-backend", type=str, default=None)
    parser.add_argument("--backend-3d", type=str, default=None)
    parser.add_argument("--collect", type=str, default=None)
    args = parser.parse_args()
    if args.collect:
        collect(pathlib.Path(args.collect))
        return
    if not args.dry_run and not args.plan:
        raise SystemExit("submitting needs a registered plan: run --dry-run first, commit it, then pass --plan")
    path = main_submit(args)
    if path is not None:
        collect(path)


if __name__ == "__main__":
    main()
