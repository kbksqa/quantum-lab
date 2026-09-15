# P6.2 helper, run with the SEPARATE QANTIS environment: builds the public repository's circuits from the paper-date commit
# 7c6509c (extracted with `git archive` into a folder outside this repository) and writes them as QPY files, so that
# src/p6_resources.py can transpile them with this project's offline IBM backend models. Nothing is copied into this project.
#
# Circuits, with the parameters the paper states or the scripts use by default:
#   minimal_listen   _build_minimal_tiger_circuit([0.85, 0.15], [0.5, 0.5], action 0, observation 0)
#   minimal_open     the same with action 2 (open-right)
#   grover_baseline  _build_baseline_circuit([0.97, 0.03], [0.85, 0.15])
#   grover1          _build_grover1_circuit([0.97, 0.03], [0.85, 0.15], target 1)
#   four_state       _build_tiger_4state_circuit([0.25] * 4, observation 0)
#   framework        QuantumBeliefUpdateCircuit(build_tiger_pomdp(), config as run_tiger_ibm.py's full mode with its default
#                    --aa-iterations 1).build(uniform, 0, 0)
#   framework_no_aa  the same with amplitude amplification off (reported only)
# It also evaluates the repository's QBRL planner (horizon 1, seed 42, as the closed-loop script configures it) on the beliefs
# of the exact-posterior loops, for comparison with src/p6_loops.py.
#
# Usage:
#     <env>/python tools/p6_export_circuits.py --tree <7c6509c tree> --out-dir <folder>

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
import traceback


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--beliefs", default=None, help="JSON list of P(tiger-left) values for the planner comparison")
    args = parser.parse_args()
    tree, out = pathlib.Path(args.tree), pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("", "packages/quantum-common/src", "packages/quantum-pomdp/src"):
        sys.path.insert(0, str(tree / sub))

    import numpy as np
    import qiskit
    from qiskit import qpy

    hardware = tree / "scripts" / "hardware"
    grover = load("q_grover", hardware / "run_grover_belief_ibm.py")
    tiger = load("q_tiger", hardware / "run_tiger_ibm.py")
    tiger4 = load("q_tiger4", hardware / "run_tiger_4state_ibm.py")

    builders = {
        "minimal_listen": lambda: tiger._build_minimal_tiger_circuit([0.85, 0.15], [0.5, 0.5], 0, 0),
        "minimal_open": lambda: tiger._build_minimal_tiger_circuit([0.85, 0.15], [0.5, 0.5], 2, 0),
        "grover_baseline": lambda: grover._build_baseline_circuit([0.97, 0.03], [0.85, 0.15]),
        "grover1": lambda: grover._build_grover1_circuit([0.97, 0.03], [0.85, 0.15], 1),
        "four_state": lambda: tiger4._build_tiger_4state_circuit([0.25] * 4, 0),
    }

    def framework(aa_iterations: int):
        """run_tiger_ibm.py full mode: _use_aa = aa_iterations > 0; the script's default is --aa-iterations 1."""
        from quantum_pomdp.models.belief_state import BeliefState
        from quantum_pomdp.quantum_circuits.belief_update import BeliefUpdateCircuitConfig, QuantumBeliefUpdateCircuit
        from scripts.hardware import build_tiger_pomdp

        pomdp = build_tiger_pomdp()
        use_aa = aa_iterations > 0
        config = BeliefUpdateCircuitConfig(use_amplitude_amplification=use_aa, use_hardware_compatible_encoding=True,
                                           reward_precision_bits=2, aa_iterations=aa_iterations if use_aa else None)
        return QuantumBeliefUpdateCircuit(pomdp=pomdp, config=config).build(
            belief=BeliefState.uniform(num_states=pomdp.num_states), action=0, observation=0)

    builders["framework"] = lambda: framework(1)            # the script's default, --aa-iterations 1
    builders["framework_no_aa"] = lambda: framework(0)      # reported only
    manifest = {"qiskit": qiskit.__version__, "tree_commit": "7c6509c", "circuits": {}}
    for name, build in builders.items():
        try:
            qc = build()
            with open(out / (name + ".qpy"), "wb") as f:
                qpy.dump(qc, f)
            manifest["circuits"][name] = {"built": True, "num_qubits": qc.num_qubits, "logical_depth": qc.depth(),
                                          "count_ops": {k: int(v) for k, v in qc.count_ops().items()}}
        except Exception as exc:  # noqa: BLE001 - a failed build is a recorded result
            manifest["circuits"][name] = {"built": False, "error": "%s: %s" % (type(exc).__name__, exc),
                                          "traceback": traceback.format_exc(limit=3)}
        print(name, manifest["circuits"][name].get("num_qubits"), manifest["circuits"][name].get("error", "ok"))

    if args.beliefs:
        from quantum_pomdp.algorithms.qbrl import QBRLConfig, QBRLPlanner
        from quantum_pomdp.models.belief_state import BeliefState
        from scripts.hardware import build_tiger_pomdp

        planner = QBRLPlanner(build_tiger_pomdp(), QBRLConfig(horizon=1, use_quantum=False, seed=42))
        beliefs = json.loads(pathlib.Path(args.beliefs).read_text(encoding="utf-8"))
        manifest["qbrl_horizon1_actions"] = [
            {"p_tiger_left": b, "action": int(planner.select_action(BeliefState(np.array([b, 1 - b]))))} for b in beliefs]
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("saved " + str(out / "manifest.json"))


if __name__ == "__main__":
    main()
