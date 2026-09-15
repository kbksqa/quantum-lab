# P6.2 - C3: are the paper's "ISA" numbers two-qubit gate counts or total depths?
#
# Paper: "ISA depth is the post-transpilation two-qubit gate count" (§8.6), reported as 12 (Tiger minimal, listen), 18 (Grover
# k = 1) and 162 (4-state), plus 13 (Grover baseline), 4 (open action) and 4,237 (full 11-qubit circuit; 4,107 and 4,309 in
# Table 18), all on IBM Heron.
#
# Method (plan): transpile at optimisation level 3 with `generate_preset_pass_manager` to the offline FakeMarrakesh model
# (Heron r2, the device named for the POMDP runs), transpiler seeds 0-19, measurements included as in the scripts. For every
# circuit record the two-qubit (CZ) count and the total depth. Circuits:
#   theirs  the public code at the paper-date commit 7c6509c, exported by tools/p6_export_circuits.py (QPY files)
#   ours    the P6.1 circuits built from the paper (src/p6_tiger.py)
#
# Grading, written before the first run. For each graded value (12, 18, 162), using their circuit when it could be built and
# ours otherwise:
#   reproduced         the stated value lies within [min, max] of the CZ count over the 20 seeds
#   partly reproduced  it lies within [min, max] of the total depth instead
#   not reproduced     neither
# C3 overall: reproduced if all three are reproduced; partly reproduced if each is at least partly reproduced; not reproduced
# otherwise. The full 11-qubit circuit is graded the same way against 4,237 if the public code builds it without modification,
# and "not reproducible" otherwise. 13 and 4 are reported without a grade.
#
# Usage:
#     python src/p6_resources.py --circuits <folder written by tools/p6_export_circuits.py>

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

import numpy as np
from qiskit import QuantumCircuit, qpy
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_ibm_runtime.fake_provider import FakeMarrakesh

from p6_tiger import OPEN_RIGHT, four_state_circuit, grover1_circuit, oracle_circuit, tiger_circuit

RESULTS = pathlib.Path(__file__).resolve().parents[1] / "results"
SEEDS = range(20)
STATED = {"minimal_listen": 12, "grover1": 18, "four_state": 162, "grover_baseline": 13, "minimal_open": 4, "framework": 4237,
          "framework_no_aa": 4237}
# framework = run_tiger_ibm.py full mode with its default --aa-iterations 1 (graded); framework_no_aa = the same with
# amplitude amplification off (reported only).
GRADED = ("minimal_listen", "grover1", "four_state")


def measured(qc: QuantumCircuit) -> QuantumCircuit:
    out = qc.copy()
    out.measure_all()
    return out


def our_circuits() -> dict:
    return {"minimal_listen": measured(tiger_circuit([0.5, 0.5], 0)),
            "minimal_open": measured(tiger_circuit([0.5, 0.5], OPEN_RIGHT)),
            "grover_baseline": measured(oracle_circuit([0.97, 0.03])),
            "grover1": measured(grover1_circuit([0.97, 0.03], 1)),
            "four_state": measured(four_state_circuit([0.25] * 4))}


def profile(qc: QuantumCircuit, backend) -> dict:
    cz, depth = [], []
    for seed in SEEDS:
        compiled = generate_preset_pass_manager(optimization_level=3, backend=backend, seed_transpiler=seed).run(qc)
        cz.append(int(compiled.count_ops().get("cz", 0)))
        depth.append(int(compiled.depth()))
    return {"cz": cz, "depth": depth, "cz_range": [min(cz), max(cz)], "depth_range": [min(depth), max(depth)],
            "cz_median": float(np.median(cz)), "depth_median": float(np.median(depth))}


def grade(stated: int, prof: dict) -> str:
    if prof["cz_range"][0] <= stated <= prof["cz_range"][1]:
        return "reproduced"
    if prof["depth_range"][0] <= stated <= prof["depth_range"][1]:
        return "partly reproduced"
    return "not reproduced"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--circuits", required=True)
    args = parser.parse_args()
    folder = pathlib.Path(args.circuits)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    backend = FakeMarrakesh()

    theirs = {}
    for name, info in manifest["circuits"].items():
        if info.get("built"):
            with open(folder / (name + ".qpy"), "rb") as f:
                theirs[name] = qpy.load(f)[0]
    record = {"timestamp": dt.datetime.now().astimezone().isoformat(),
              "experiment": "P6.2 C3: circuit sizes on the offline FakeMarrakesh model, optimisation level 3, seeds 0-19",
              "backend": backend.name, "export_manifest": manifest, "circuits": {}}
    ours = our_circuits()
    for name, stated in STATED.items():
        row = {"stated": stated}
        if name in ours:
            row["ours"] = profile(ours[name], backend)
        if name in theirs:
            row["theirs"] = profile(theirs[name], backend)
        basis = row.get("theirs") or row.get("ours")
        if name in GRADED:
            row["grade"] = grade(stated, basis)
            row["graded_on"] = "theirs" if "theirs" in row else "ours"
        elif name == "framework":
            row["grade"] = grade(stated, row["theirs"]) if "theirs" in row else "not reproducible"
        record["circuits"][name] = row
        print("%-16s stated %5d  %s" % (name, stated, {k: (v["cz_range"], v["depth_range"]) for k, v in row.items()
                                                        if isinstance(v, dict)}), row.get("grade", ""), flush=True)
    grades = [record["circuits"][n]["grade"] for n in GRADED]
    record["C3_overall"] = ("reproduced" if all(g == "reproduced" for g in grades) else
                            "partly reproduced" if all(g != "not reproduced" for g in grades) else "not reproduced")
    record["framework_grade"] = record["circuits"]["framework"]["grade"]
    print("C3 overall: %s; framework: %s" % (record["C3_overall"], record["framework_grade"]))
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p6_2-resources-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
