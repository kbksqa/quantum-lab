# P6.1 cross-check against the QANTIS public repository, run with a SEPARATE Python environment and a clone of
# https://github.com/neuraparse/qantis. Nothing from the repository is copied into this project: the circuit builders are
# imported at run time from the paper-date versions of the scripts (commit 7c6509c), extracted with `git show` into a folder
# outside this repository.
#
# For each builder, the final measurements are removed and the exact statevector is compared with this project's circuit and
# with exact Bayes:
#   - _build_baseline_circuit / _build_grover1_circuit (run_grover_belief_ibm.py): P(obs = 1) and the post-selected posterior
#   - _build_minimal_tiger_circuit (run_tiger_ibm.py): posteriors for listen and open actions, both observations
#   - _build_tiger_4state_circuit (run_tiger_4state_ibm.py): posteriors for both observations; their state index is
#     s = 2 q0 + q1, ours is s = q0 + 2 q1
#
# Usage (from the quantum-lab repository root):
#     <env>/python tools/p6_repo_crosscheck.py --qantis-repo <clone> --scripts <folder with the 7c6509c scripts> --out <json>

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import pathlib
import subprocess
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def unmeasured_probabilities(qc) -> np.ndarray:
    from qiskit.quantum_info import Statevector

    return np.abs(Statevector(qc.remove_final_measurements(inplace=False)).data) ** 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qantis-repo", required=True)
    parser.add_argument("--scripts", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    repo, scripts = pathlib.Path(args.qantis_repo), pathlib.Path(args.scripts)
    sys.path.insert(0, str(repo))

    import qiskit

    from p6_tiger import (LISTEN, OPEN_RIGHT, P_OBS0_2, P_OBS0_4, C2_PRIORS_2, bayes, four_state_circuit, grover1_circuit,
                          hellinger, oracle_circuit, post_select, statevector, tiger_circuit)

    grover = load("qantis_grover", scripts / "run_grover_belief_ibm.py")
    tiger = load("qantis_tiger", scripts / "run_tiger_ibm.py")
    tiger4 = load("qantis_tiger4", scripts / "run_tiger_4state_ibm.py")
    record = {"timestamp": dt.datetime.now().astimezone().isoformat(),
              "experiment": "P6.1 cross-check against the QANTIS public repository (scripts at 7c6509c)",
              "repository_head": subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                                                text=True).stdout.strip(),
              "scripts_commit": "7c6509c", "environment": {"python": sys.version.split()[0], "qiskit": qiskit.__version__}}

    prior, target = [0.97, 0.03], 1
    theirs_base = unmeasured_probabilities(grover._build_baseline_circuit(prior, [0.85, 0.15]))
    theirs_grover = unmeasured_probabilities(grover._build_grover1_circuit(prior, [0.85, 0.15], target))
    ours_base = np.abs(statevector(oracle_circuit(prior))) ** 2
    ours_grover = np.abs(statevector(grover1_circuit(prior, target))) ** 2
    record["grover"] = {
        "their_p_obs1_baseline": float(theirs_base.reshape(2, 2)[target].sum()),
        "their_p_obs1_grover": float(theirs_grover.reshape(2, 2)[target].sum()),
        "their_posterior": post_select(theirs_grover, 2, target)[0].tolist(),
        "max_probability_difference_to_ours": float(max(np.max(np.abs(theirs_base - ours_base)),
                                                        np.max(np.abs(theirs_grover - ours_grover)))),
    }

    worst = {"listen": 0.0, "open": 0.0}
    for b in C2_PRIORS_2:
        prior2 = [b, 1 - b]
        for action, key in ((LISTEN, "listen"), (OPEN_RIGHT, "open")):
            theirs = unmeasured_probabilities(tiger._build_minimal_tiger_circuit([0.85, 0.15], prior2, action, 0))
            ours = np.abs(statevector(tiger_circuit(prior2, action))) ** 2
            for obs in (0, 1):
                worst[key] = max(worst[key], hellinger(post_select(theirs, 2, obs)[0], bayes(prior2, P_OBS0_2, obs, action)[0]),
                                 float(np.max(np.abs(theirs - ours))))
    record["minimal"] = {"priors": len(C2_PRIORS_2), "max_hellinger_or_probability_difference": worst}

    uniform = [0.25] * 4
    theirs4 = unmeasured_probabilities(tiger4._build_tiger_4state_circuit(uniform, 0))
    # their index: q0 = state MSB, q1 = state LSB, q2 = observation; convert to ours (s = q0 + 2 q1)
    remapped = np.zeros(8)
    for index, p in enumerate(theirs4):
        q0, q1, q2 = index & 1, (index >> 1) & 1, (index >> 2) & 1
        s_theirs = 2 * q0 + q1
        remapped[s_theirs + 4 * q2] += p
    ours4 = np.abs(statevector(four_state_circuit(uniform))) ** 2
    record["four_state"] = {
        "their_posteriors": {str(obs): post_select(remapped, 4, obs)[0].tolist() for obs in (0, 1)},
        "max_hellinger_to_bayes": max(hellinger(post_select(remapped, 4, obs)[0], bayes(uniform, P_OBS0_4, obs)[0])
                                      for obs in (0, 1)),
        "max_probability_difference_to_ours": float(np.max(np.abs(remapped - ours4))),
        "same_circuit_for_both_observations": bool(np.allclose(
            unmeasured_probabilities(tiger4._build_tiger_4state_circuit(uniform, 0)),
            unmeasured_probabilities(tiger4._build_tiger_4state_circuit(uniform, 1)))),
    }
    print(json.dumps(record, indent=1))
    out = pathlib.Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
