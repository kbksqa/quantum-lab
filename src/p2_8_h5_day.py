# P2.8 / O1 - H5, day half: the P1.5 2x2 p = 2 circuits again on ibm_kingston, the P1.5 device, on a later calendar day.
#
# Registered in docs/p2-plan.md, Amendment 2. As in P2.6 experiment A, except that the device is fixed in advance instead of
# being chosen by the day's ranking, so that only the day changes:
#   - the same 10 instances and stored parameters, checked against the simulator to 1e-9 (p2_6_hardware.h5_items)
#   - tensored readout correction from all-0 / all-1 calibration circuits, 2048 shots, one job
#   - if ibm_kingston is unavailable, or it is still 2026-09-14, nothing is submitted
#
# H5-day: corrected retention within 0.05 of P1.5's 0.890 is held, within 0.10 partly held, and otherwise failed.
#
# Usage:
#     python src/p2_8_h5_day.py --dry-run                                    # transpile and save a plan, submit nothing
#     python src/p2_8_h5_day.py --plan results/p2_8-h5-plan-XXXX.json        # submit exactly that plan, then collect
#     python src/p2_8_h5_day.py --collect results/p2_8-h5-hardware-XXXX-submitted.json

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

from p2_scene import RESULTS

DEVICE = "ibm_kingston"
P1_5_DAY = dt.date(2026, 9, 14)
P1_5_RETENTION = 0.890
SHOTS = 2048
PREFIX = "p2_8-h5-hardware"


def grade(retention: float) -> str:
    distance = abs(retention - P1_5_RETENTION)
    return "held" if distance <= 0.05 + 1e-12 else ("partly held" if distance <= 0.10 + 1e-12 else "failed")


def today_after_p1_5() -> str:
    today = dt.datetime.now().astimezone().date()
    if today <= P1_5_DAY:
        raise SystemExit("still the calendar day of P1.5 (%s) - nothing submitted" % P1_5_DAY)
    return today.isoformat()


def main_submit(args) -> pathlib.Path | None:
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    from p1_5_hardware import calibration_pair, rank_devices
    from p2_6_hardware import compile_items, describe, h5_items

    day = today_after_p1_5()
    service = QiskitRuntimeService()
    try:
        backend = service.backend(DEVICE)
        operational = backend.status().operational
    except Exception as exc:  # noqa: BLE001 - any failure to reach the device stops the run
        raise SystemExit("%s is unavailable (%s) - nothing submitted, revise the plan" % (DEVICE, exc))
    if not operational:
        raise SystemExit("%s is not operational - nothing submitted, revise the plan" % DEVICE)

    ranking = rank_devices(service)
    for r in ranking:
        print("  %-14s median CZ error %.4f   median readout error %.4f"
              % (r["backend"], r["median_cz_error"], r["median_readout_error"]))
    items = h5_items()
    compile_items(items, backend)
    union = sorted({q for it in items for q in it["measured_physical_qubits"]})
    experiments = {"A": {"backend": backend.name, "items": items, "union": union,
                         "calibration": calibration_pair(union, backend)}}
    summary = describe(experiments)
    s = summary["A"]
    print("H5 day half on %s: instances %s, CZ %s, simulator P(opt) %.4f, %d circuits"
          % (s["backend"], s["instances"], s["two_qubit_gates"], s["simulator_p_optimal_mean"], s["circuits"]))

    if args.plan:
        plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))
        registered = plan["experiments"]["A"]
        if registered["backend"] != DEVICE or registered["instances"] != s["instances"]:
            raise SystemExit("the plan does not describe this run - stop")
        if registered["two_qubit_gates"] != s["two_qubit_gates"]:
            print("note: CZ counts changed since the plan: %s -> %s" % (registered["two_qubit_gates"], s["two_qubit_gates"]))

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    record = {"stamp": stamp, "experiment": "P2.8 O1: H5 day half", "day": day, "p1_5_day": P1_5_DAY.isoformat(),
              "device_ranking": ranking, "shots": SHOTS, "total_shots": s["circuits"] * SHOTS, "experiments": summary,
              "grading": "|retention - %.3f| <= 0.05 held, <= 0.10 partly held, otherwise failed" % P1_5_RETENTION}
    if args.dry_run:
        path = RESULTS / ("p2_8-h5-plan-%s.json" % stamp)
        record["status"] = "plan (dry run, nothing submitted)"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print("dry run - nothing submitted - plan saved " + str(path))
        return None

    record["plan_file"] = args.plan
    job = SamplerV2(mode=backend).run([it["compiled"] for it in items] + experiments["A"]["calibration"], shots=SHOTS)
    record["experiments"]["A"]["job_id"] = job.job_id()
    record["status"] = "submitted"
    record["submitted_at"] = dt.datetime.now().astimezone().isoformat()
    print("submitted: job %s on %s" % (job.job_id(), backend.name))
    path = RESULTS / ("%s-%s-submitted.json" % (PREFIX, stamp))
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(path))
    return path


def collect(path: pathlib.Path) -> None:
    from p2_6_hardware import collect as collect_p2_6

    out = collect_p2_6(path, prefix=PREFIX)
    record = json.loads(out.read_text(encoding="utf-8"))
    retention = record["experiments"]["A"]["summary"]["retention_corrected"]
    record["h5_day_verdict"] = {"retention_corrected": retention, "p1_5_retention": P1_5_RETENTION,
                                "distance": abs(retention - P1_5_RETENTION), "H5_day": grade(retention)}
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("H5-day: %s" % record["h5_day_verdict"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan", type=str, default=None)
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
