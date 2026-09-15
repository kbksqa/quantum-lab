# P6.4 - QANTIS POMDP half on hardware: the Grover k = 1 experiment (paper §8.6, Table 15), three replicates.
#
# Registered in docs/p6-plan.md (hardware rules). Go rule, all three required:
#   - C1 reproduced (results/p6_1-tiger-20260915-150853.json)
#   - C3 at least partly reproduced for the Grover circuit (results/p6_2-resources-20260915-152850.json)
#   - a dry-run QPU-time estimate for the three replicates within 60 s
# QPU-time estimate, fixed here before the dry run: this project's jobs have reported 9 s each for up to 49,152 shots (P2.6,
# P2.8). Estimate = 9 s x max(1, total shots / 49,152) x 2, the factor 2 allowing for the overhead of Pauli twirling.
#
# Experiment, as the paper describes it: prior [0.97, 0.03], target observation 1 (hear-right); the belief oracle A (baseline)
# and one Grover iterate A S0 A^dagger S_f A, both rebuilt from the paper in src/p6_tiger.py (P6.1 showed they give the same
# probabilities as the public code). Nothing is optimised on hardware.
#   - one job on the device with the lowest median CZ error that day (ibm_kingston, ibm_fez, ibm_marrakesh), 8,192 shots per
#     circuit; the three replicates are three copies of the baseline + Grover pair in that job
#   - the paper's mitigation as documented: Pauli twirling on gates with 32 randomisations, XY4 dynamical decoupling; the ZNE
#     that §8.6 mentions "where noted" is not used for this experiment in the paper and is not used here
#   - readout calibration circuits (all-0 / all-1) on the measured qubits in the same job, as in every earlier hardware run of
#     this project; raw values are the headline because the paper does not state a readout correction
#
# Grading of the hardware claim, fixed before submission (mean over the three replicates, raw counts):
#   paper: P(obs = 1) 0.179 -> 0.907, amplification 5.1x, post-selected posterior [0.849, 0.151] (Hellinger 0.0015)
#   reproduced if all three hold, partly reproduced if two hold, not reproduced otherwise:
#     (a) Grover P(obs = 1) within 0.03 of 0.907   (b) amplification within 0.5 of 5.1
#     (c) Hellinger distance of the post-selected posterior to exact Bayes below 0.05
#
# Usage:
#     python src/p6_hardware.py --dry-run
#     python src/p6_hardware.py --plan results/p6_4-plan-XXXX.json
#     python src/p6_hardware.py --collect results/p6_4-hardware-XXXX-submitted.json

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib

import numpy as np

from p6_tiger import P_OBS0_2, bayes, grover1_circuit, hellinger, oracle_circuit

RESULTS = pathlib.Path(__file__).resolve().parents[1] / "results"
PRIOR, TARGET = [0.97, 0.03], 1
REPLICATES, SHOTS, RANDOMIZATIONS = 3, 8192, 32
BUDGET_SECONDS, BASIS_JOB_SECONDS, BASIS_SHOTS, TWIRL_FACTOR = 60.0, 9.0, 49152, 2.0
C1_FILE = RESULTS / "p6_1-tiger-20260915-150853.json"
C3_FILE = RESULTS / "p6_2-resources-20260915-152850.json"
PAPER = {"p_obs1_baseline": 0.179, "p_obs1_grover": 0.907, "amplification": 5.1, "posterior": [0.849, 0.151]}

# Predictions, committed before any submission (graded on the raw means over the replicates).
PREDICTIONS = {
    "E1_baseline_p_obs1": (0.160, 0.195),
    "E2_grover_p_obs1": (0.860, 0.930),
    "E3_amplification": (4.5, 5.6),
    "E4_posterior_hellinger_below": 0.02,
    "E5_grover_over_direct_per_oracle_application": (1.5, 1.9),
}


def estimate_seconds(total_shots: int) -> float:
    return BASIS_JOB_SECONDS * max(1.0, total_shots / BASIS_SHOTS) * TWIRL_FACTOR


def go_rule(total_shots: int) -> dict:
    c1 = json.loads(C1_FILE.read_text(encoding="utf-8"))["C1"]["grade"]
    c3 = json.loads(C3_FILE.read_text(encoding="utf-8"))["circuits"]["grover1"]["grade"]
    estimate = estimate_seconds(total_shots)
    return {"C1": c1, "C3_grover": c3, "estimated_qpu_seconds": estimate, "budget_seconds": BUDGET_SECONDS,
            "go": c1 == "reproduced" and c3 in ("reproduced", "partly reproduced") and estimate <= BUDGET_SECONDS}


def metrics(base_probs: np.ndarray, grover_probs: np.ndarray) -> dict:
    """Probabilities indexed s + 2 o (q0 = state, q1 = observation)."""
    p_base = float(base_probs[2] + base_probs[3])
    p_grover = float(grover_probs[2] + grover_probs[3])
    posterior = np.array([grover_probs[2], grover_probs[3]]) / p_grover
    exact, _ = bayes(PRIOR, P_OBS0_2, TARGET)
    return {"p_obs1_baseline": p_base, "p_obs1_grover": p_grover, "amplification": p_grover / p_base,
            "posterior": posterior.tolist(), "posterior_hellinger": hellinger(posterior, exact),
            "grover_over_direct_per_oracle_application": (p_grover / 3) / p_base}


def grade_claim(mean: dict) -> dict:
    checks = {"a_grover_p_within_0.03_of_0.907": abs(mean["p_obs1_grover"] - PAPER["p_obs1_grover"]) <= 0.03,
              "b_amplification_within_0.5_of_5.1": abs(mean["amplification"] - PAPER["amplification"]) <= 0.5,
              "c_posterior_hellinger_below_0.05": mean["posterior_hellinger"] < 0.05}
    held = sum(checks.values())
    return {"checks": checks, "grade": "reproduced" if held == 3 else ("partly reproduced" if held == 2 else "not reproduced")}


def grade_predictions(mean: dict) -> dict:
    inside = lambda v, r: r[0] <= v <= r[1]  # noqa: E731
    return {
        "E1": inside(mean["p_obs1_baseline"], PREDICTIONS["E1_baseline_p_obs1"]),
        "E2": inside(mean["p_obs1_grover"], PREDICTIONS["E2_grover_p_obs1"]),
        "E3": inside(mean["amplification"], PREDICTIONS["E3_amplification"]),
        "E4": mean["posterior_hellinger"] < PREDICTIONS["E4_posterior_hellinger_below"],
        "E5": inside(mean["grover_over_direct_per_oracle_application"],
                     PREDICTIONS["E5_grover_over_direct_per_oracle_application"]),
    }


def mean_metrics(rows: list) -> dict:
    keys = ("p_obs1_baseline", "p_obs1_grover", "amplification", "posterior_hellinger",
            "grover_over_direct_per_oracle_application")
    out = {k: float(np.mean([r[k] for r in rows])) for k in keys}
    out.update({k + "_sd": float(np.std([r[k] for r in rows], ddof=1)) for k in keys})
    return out


# ---------------------------------------------------------------- IBM parts

def build(service, device: str) -> dict:
    from qiskit.transpiler import generate_preset_pass_manager

    from p0_5_readout import measured_physical_qubits
    from p1_5_hardware import calibration_pair

    backend = service.backend(device)
    pm = generate_preset_pass_manager(optimization_level=3, backend=backend, seed_transpiler=7)
    base = oracle_circuit(PRIOR)
    base.measure_all()
    grover = grover1_circuit(PRIOR, TARGET)
    grover.measure_all()
    compiled = {"baseline": pm.run(base), "grover1": pm.run(grover)}
    info = {name: {"two_qubit_gates": int(c.count_ops().get("cz", 0)), "depth": c.depth(),
                   "measured_physical_qubits": measured_physical_qubits(c)} for name, c in compiled.items()}
    union = sorted({q for v in info.values() for q in v["measured_physical_qubits"]})
    pubs = [compiled[name] for _ in range(REPLICATES) for name in ("baseline", "grover1")] + calibration_pair(union, backend)
    return {"backend": backend, "compiled": compiled, "info": info, "union": union, "pubs": pubs}


def main_submit(args) -> pathlib.Path | None:
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    from p1_5_hardware import rank_devices

    service = QiskitRuntimeService()
    if args.plan:
        plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))
        device, ranking = plan["backend"], plan["device_ranking"]
    else:
        ranking = rank_devices(service)
        device = ranking[0]["backend"]
    for r in ranking:
        print("  %-14s median CZ error %.4f   median readout error %.4f"
              % (r["backend"], r["median_cz_error"], r["median_readout_error"]))
    built = build(service, device)
    total_shots = len(built["pubs"]) * SHOTS
    go = go_rule(total_shots)
    print("device %s: %s; union %s; %d circuits, %d shots; go rule %s"
          % (device, built["info"], built["union"], len(built["pubs"]), total_shots, go))
    if args.plan and built["info"] != plan["circuits"]:
        print("note: transpiled circuits differ from the plan: %s -> %s" % (plan["circuits"], built["info"]))
    if not go["go"]:
        raise SystemExit("go rule not met - nothing submitted")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    record = {"stamp": stamp, "experiment": "P6.4 Grover k = 1 on hardware (QANTIS §8.6)", "backend": device,
              "device_ranking": ranking, "circuits": built["info"], "union": built["union"], "replicates": REPLICATES,
              "shots": SHOTS, "total_shots": total_shots, "twirling": {"enable_gates": True, "num_randomizations": RANDOMIZATIONS},
              "dynamical_decoupling": "XY4", "go_rule": go, "predictions": PREDICTIONS, "paper": PAPER}
    if args.dry_run:
        path = RESULTS / ("p6_4-plan-%s.json" % stamp)
        record["status"] = "plan (dry run, nothing submitted)"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print("dry run - nothing submitted - plan saved " + str(path))
        return None

    sampler = SamplerV2(mode=built["backend"])
    sampler.options.twirling.enable_gates = True
    sampler.options.twirling.num_randomizations = RANDOMIZATIONS
    sampler.options.dynamical_decoupling.enable = True
    sampler.options.dynamical_decoupling.sequence_type = "XY4"
    job = sampler.run(built["pubs"], shots=SHOTS)
    record.update(status="submitted", plan_file=args.plan, job_id=job.job_id(),
                  submitted_at=dt.datetime.now().astimezone().isoformat())
    path = RESULTS / ("p6_4-hardware-%s-submitted.json" % stamp)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("submitted job %s on %s; saved %s" % (job.job_id(), device, path))
    return path


def collect(path: pathlib.Path) -> None:
    from qiskit_ibm_runtime import QiskitRuntimeService

    from p1_5_hardware import counts_to_probs, per_qubit_errors, tensored_correct

    record = json.loads(path.read_text(encoding="utf-8"))
    job = QiskitRuntimeService().job(record["job_id"])
    result = job.result()
    n = 2 * REPLICATES
    errors = per_qubit_errors(result[n].data.c.get_counts(), result[n + 1].data.c.get_counts(), record["union"])
    raw_rows, corrected_rows, counts = [], [], []
    for r in range(REPLICATES):
        probs = {}
        for k, name in enumerate(("baseline", "grover1")):
            c = result[2 * r + k].data.meas.get_counts()
            counts.append({"replicate": r, "circuit": name, "counts": c})
            raw = counts_to_probs(c, 2)
            probs[name] = (raw, tensored_correct(raw, record["circuits"][name]["measured_physical_qubits"], errors))
        raw_rows.append(metrics(probs["baseline"][0], probs["grover1"][0]))
        corrected_rows.append(metrics(probs["baseline"][1], probs["grover1"][1]))
    raw_mean, corrected_mean = mean_metrics(raw_rows), mean_metrics(corrected_rows)
    try:
        usage = job.usage()
    except Exception as exc:  # noqa: BLE001 - usage reporting is optional
        usage = "unavailable: %s" % exc
    record.update(status="done", finished_at=dt.datetime.now().astimezone().isoformat(), usage_seconds=usage,
                  per_qubit_errors={str(q): list(v) for q, v in errors.items()}, counts=counts,
                  replicates_raw=raw_rows, replicates_corrected=corrected_rows, mean_raw=raw_mean,
                  mean_corrected=corrected_mean, claim=grade_claim(raw_mean), predictions_held=grade_predictions(raw_mean),
                  claim_on_corrected=grade_claim(corrected_mean))
    out = RESULTS / ("p6_4-hardware-%s.json" % record["stamp"])
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("usage_seconds", "mean_raw", "mean_corrected", "claim", "predictions_held")},
                     indent=1))
    print("saved " + str(out))


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
