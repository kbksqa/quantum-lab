# P0 - Analysis of the hardware Grover sweep.
#
# Two questions:
#   1. How well does a single global depolarizing model explain the hardware numbers?
#      p_hw = f * p_theory + (1 - f) / 2^n   ->   f = (p_hw - 1/2^n) / (p_theory - 1/2^n)
#      and, if all loss came from two-qubit gates, a per-gate fidelity F = f^(1 / n_2q).
#      f is only meaningful when p_theory is far from 1/2^n, so each point is flagged.
#   2. Is the noise uniform? At the best iteration count, compare the probability of wrong
#      outcomes grouped by Hamming distance from the marked state with what a uniform
#      depolarizing channel would predict.
#
# Usage:
#     python src/p0_hardware_analysis.py                                   # latest hardware result
#     python src/p0_hardware_analysis.py --file results/p0-hardware-sweep-XXXX.json

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib

from p0_grover import RESULTS

RELIABILITY_THRESHOLD = 0.25  # |p_theory - 1/2^n| below this makes f too sensitive to shot noise


def latest_hardware_file() -> pathlib.Path:
    files = sorted(p for p in RESULTS.glob("p0-hardware-sweep-*.json") if "submitted" not in p.name)
    if not files:
        raise SystemExit("no hardware sweep result found in results/")
    return files[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default=None)
    args = parser.parse_args()

    source = pathlib.Path(args.file) if args.file else latest_hardware_file()
    data = json.loads(source.read_text(encoding="utf-8"))
    n = data["qubits"]
    marked = data["marked"]
    baseline = 1 / 2 ** n

    fits = []
    print("k | 2q | theory | hardware | f      | F per 2q gate | reliable")
    for row in data["rows"]:
        spread = row["theory"] - baseline
        n2q = row.get("two_qubit_gates", 0)
        if abs(spread) < 1e-9:
            f = None
        else:
            f = (row["hardware"] - baseline) / spread
        per_gate = f ** (1 / n2q) if (f is not None and f > 0 and n2q > 0) else None
        reliable = f is not None and abs(spread) >= RELIABILITY_THRESHOLD
        fits.append(
            {
                "iterations": row["iterations"],
                "two_qubit_gates": n2q,
                "theory": row["theory"],
                "hardware": row["hardware"],
                "effective_fidelity": f,
                "per_two_qubit_gate_fidelity": per_gate,
                "reliable": reliable,
            }
        )
        print(
            "%d | %2d | %.4f | %.4f   | %6s | %13s | %s"
            % (
                row["iterations"],
                n2q,
                row["theory"],
                row["hardware"],
                "-" if f is None else "%.3f" % f,
                "-" if per_gate is None else "%.4f" % per_gate,
                "yes" if reliable else "no",
            )
        )

    best = max(data["rows"], key=lambda r: r["theory"])
    total = sum(best["counts"].values())
    by_distance: dict[int, int] = {}
    for bits, count in best["counts"].items():
        distance = sum(a != b for a, b in zip(bits, marked))
        by_distance[distance] = by_distance.get(distance, 0) + count

    best_fit = next(x for x in fits if x["iterations"] == best["iterations"])
    uniform_error_per_state = (1 - best_fit["effective_fidelity"]) * baseline

    anatomy = []
    print()
    print("error anatomy at k=%d (uniform depolarizing would give %.4f per wrong state)"
          % (best["iterations"], uniform_error_per_state))
    for distance in sorted(by_distance):
        states = math.comb(n, distance)
        share = by_distance[distance] / total
        anatomy.append(
            {
                "hamming_distance": distance,
                "states": states,
                "shots": by_distance[distance],
                "probability": share,
                "probability_per_state": share / states,
            }
        )
        print("distance %d: %4d shots, %.4f total, %.4f per state"
              % (distance, by_distance[distance], share, share / states))

    reliable_gates = [x["per_two_qubit_gate_fidelity"] for x in fits
                      if x["reliable"] and x["per_two_qubit_gate_fidelity"] is not None]

    record = {
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P0 hardware analysis",
        "source": source.name,
        "backend": data["backend"],
        "job_id": data["job_id"],
        "model": "global depolarizing: p_hw = f * p_theory + (1 - f) / 2^n",
        "reliability_threshold": RELIABILITY_THRESHOLD,
        "fits": fits,
        "per_two_qubit_gate_fidelity_range_reliable": [min(reliable_gates), max(reliable_gates)] if reliable_gates else None,
        "error_anatomy_iteration": best["iterations"],
        "uniform_error_per_wrong_state": uniform_error_per_state,
        "error_anatomy": anatomy,
    }
    out = RESULTS / ("p0-hardware-analysis-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
