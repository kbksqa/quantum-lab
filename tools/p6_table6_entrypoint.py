# P6.3 helper, run with the SEPARATE QANTIS environment: executes the public simulation entry point's POMDP branch,
# `_run_pomdp_experiment` in scripts/run_experiment.py at the paper-date commit 7c6509c, unmodified.
#
# The script's own `main()` only loads the YAML file (PyYAML, pydantic, structlog) and sets up logging before calling this
# function. Those packages are not installed in the separate environment, so this harness passes the function an object whose
# `case_parameters` holds exactly the values of configs/experiments/pomdp_default.yaml at 7c6509c, and captures its log output.
# Nothing is installed and nothing from the repository is copied into this project.
#
# Usage:
#     <env>/python tools/p6_table6_entrypoint.py --tree <7c6509c tree> --out <json>

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import io
import json
import logging
import pathlib
import sys
import time

# configs/experiments/pomdp_default.yaml at 7c6509c, case_parameters section (the parts the POMDP branch reads)
CASE_PARAMETERS = {
    "scenario": "tiger",
    "tiger": {"listen_accuracy": 0.85, "num_episodes": 100, "max_steps_per_episode": 20},
    "qbrl": {"horizon": 2, "num_samples": 100, "use_quantum": True, "use_amplitude_amplification": True, "aa_iterations": 1},
    "baselines": ["pomcp", "pbvi", "despot"],
}


class Config:
    name = "pomdp_belief_estimation"
    case_parameters = CASE_PARAMETERS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    tree = pathlib.Path(args.tree)
    for sub in ("", "packages/quantum-common/src", "packages/quantum-pomdp/src"):
        sys.path.insert(0, str(tree / sub))

    spec = importlib.util.spec_from_file_location("qantis_run_experiment", tree / "scripts" / "run_experiment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    stream = io.StringIO()
    logger = logging.getLogger("qantis_run_experiment")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)

    start = time.perf_counter()
    error = None
    try:
        module._run_pomdp_experiment(Config(), logger)
    except Exception as exc:  # noqa: BLE001 - a failure is a recorded result
        error = "%s: %s" % (type(exc).__name__, exc)
    lines = stream.getvalue().splitlines()
    record = {"timestamp": dt.datetime.now().astimezone().isoformat(),
              "experiment": "P6.3 public simulation entry point (_run_pomdp_experiment at 7c6509c, default config)",
              "case_parameters": CASE_PARAMETERS, "seconds": time.perf_counter() - start, "error": error,
              "log": lines}
    print("\n".join(lines))
    print("error:", error)
    out = pathlib.Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
