# P6.3 - C5: can Table 6 of the QANTIS paper be reproduced?
#
# Table 6 (§8.2.1): Tiger, mean cumulative reward (± std. dev.) over 100 episodes of 50 steps, Qiskit Aer, seed 42, horizon H = 5:
#     POMCP 18.3 ± 12.7   DESPOT 19.1 ± 11.4   PBVI 17.6 ± 13.2   QBRL (sim.) 18.7 ± 12.1
#
# Grading, written before the first run (the plan fixes the claim; this makes it operational):
#   Attempt A - the public entry point. `_run_pomdp_experiment` in scripts/run_experiment.py at the paper-date commit, with its
#     default configuration, run unmodified by tools/p6_table6_entrypoint.py. It reproduces Table 6 only if it reports, for each
#     of the four planners, a mean and a standard deviation over 100 episodes of 50 steps, each mean within the table's stated
#     standard deviation of the table's value.
#   Attempt B - a protocol fully determined by the paper. The paper states episodes (100), steps (50), horizon (5), seed (42)
#     and gamma (0.95). It does not state the rewards (only the public code does), whether the reported reward is discounted,
#     what happens after a door is opened, or how the tiger is placed. If any of these is missing, no protocol is fully
#     determined and attempt B is not available.
#   C5: reproduced if A or B reproduces the table; not reproduced if B is available and misses; not reproducible otherwise.
#
# Exploratory, not graded: plausible protocols the paper leaves open, run with two policies that plan exactly - a horizon-5
# lookahead (the table's H) and the optimal policy from value iteration (P6.2) - to see whether any protocol gives values
# like the table's. 100 episodes x 50 steps, seed 42 for each row. Protocol choices:
#     after an open action: the tiger is re-placed uniformly and the belief reset to 0.5 (continue), or the episode ends
#     reward: undiscounted sum, or discounted by gamma^t
#
# Usage:
#     python src/p6_table6.py --entrypoint results/p6_3-entrypoint-XXXX.json

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import pathlib

import numpy as np

from p6_loops import (ACCURACY, GAMMA, LISTEN, OPEN_LEFT, OPEN_RIGHT, R_LISTEN, R_TIGER, R_TREASURE, expected_reward,
                      optimal_policy_from, update, value_iteration)

RESULTS = pathlib.Path(__file__).resolve().parents[1] / "results"
TABLE6 = {"POMCP": (18.3, 12.7), "DESPOT": (19.1, 11.4), "PBVI": (17.6, 13.2), "QBRL (sim.)": (18.7, 12.1)}
PAPER_STATES = {"episodes": 100, "steps": 50, "horizon": 5, "seed": 42, "gamma": 0.95}
PAPER_OMITS = ["rewards", "discounting of the reported reward", "what happens after a door is opened",
               "initial placement of the tiger"]


@functools.lru_cache(maxsize=None)
def lookahead_value(p_key: int, depth: int) -> float:
    """Exact H-step value with leaf value 0; p_key = round(p * 1e9)."""
    if depth == 0:
        return 0.0
    p = p_key / 1e9
    return max(q_value(p, a, depth) for a in (LISTEN, OPEN_LEFT, OPEN_RIGHT))


def q_value(p: float, action: int, depth: int) -> float:
    reward = float(expected_reward(p, action))
    if depth == 1:
        return reward
    if action != LISTEN:
        return reward + GAMMA * lookahead_value(int(round(0.5 * 1e9)), depth - 1)
    p_obs1 = ACCURACY * p + (1 - ACCURACY) * (1 - p)
    future = 0.0
    for obs, prob in ((1, p_obs1), (0, 1 - p_obs1)):
        if prob > 0:
            future += prob * lookahead_value(int(round(update(p, obs, LISTEN) * 1e9)), depth - 1)
    return reward + GAMMA * future


def lookahead_policy(horizon: int):
    def act(p: float) -> int:
        values = [q_value(p, a, horizon) for a in (LISTEN, OPEN_LEFT, OPEN_RIGHT)]
        return int(max(range(3), key=lambda a: values[a]))
    return act


def run_protocol(policy, after_open: str, discounted: bool, episodes: int = 100, steps: int = 50, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    totals, opens = [], []
    for _ in range(episodes):
        tiger_right = rng.random() < 0.5
        p, total, n_open = 0.5, 0.0, 0
        for t in range(steps):
            action = policy(p)
            weight = GAMMA ** t if discounted else 1.0
            if action == LISTEN:
                total += weight * R_LISTEN
                correct = rng.random() < ACCURACY
                p = update(p, int(tiger_right) if correct else int(not tiger_right), LISTEN)
            else:
                good = (action == OPEN_LEFT and tiger_right) or (action == OPEN_RIGHT and not tiger_right)
                total += weight * (R_TREASURE if good else R_TIGER)
                n_open += 1
                if after_open == "end":
                    break
                tiger_right = rng.random() < 0.5
                p = 0.5
        totals.append(total)
        opens.append(n_open)
    return {"mean": float(np.mean(totals)), "sd": float(np.std(totals, ddof=1)), "mean_opens": float(np.mean(opens))}


def attempt_a(entrypoint: dict) -> dict:
    log = entrypoint.get("log", [])
    reports_planners = all(any(name.split(" ")[0].lower() in line.lower() for line in log) for name in TABLE6)
    reports_sd = any("std" in line.lower() or "±" in line for line in log)
    return {"error": entrypoint.get("error"), "seconds": entrypoint.get("seconds"),
            "case_parameters": entrypoint.get("case_parameters"),
            "final_log_lines": log[-3:], "reports_all_four_planners": reports_planners, "reports_standard_deviation": reports_sd,
            "reproduces_table6": False if not (reports_planners and reports_sd) else None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entrypoint", required=True)
    args = parser.parse_args()
    entry = json.loads(pathlib.Path(args.entrypoint).read_text(encoding="utf-8"))
    a = attempt_a(entry)
    b = {"available": not PAPER_OMITS, "paper_states": PAPER_STATES, "paper_omits": PAPER_OMITS}
    if a["reproduces_table6"] is None:
        raise SystemExit("attempt A reports per-planner means and deviations - grade it by hand against the rule")
    grade = "reproduced" if a["reproduces_table6"] else ("not reproduced" if b["available"] else "not reproducible")

    optimal = optimal_policy_from(value_iteration())
    h5 = lookahead_policy(5)
    rows = []
    for after_open in ("continue", "end"):
        for discounted in (False, True):
            for name, policy in (("horizon-5 lookahead", h5), ("optimal (value iteration)", optimal)):
                row = {"after_open": after_open, "discounted": discounted, "policy": name,
                       **run_protocol(policy, after_open, discounted)}
                row["within_sd_of_QBRL_18.7"] = abs(row["mean"] - 18.7) <= 12.1
                rows.append(row)
                print("%-9s %-12s %-26s mean %7.2f  sd %6.2f  opens/episode %.2f"
                      % (after_open, "discounted" if discounted else "undiscounted", name, row["mean"], row["sd"],
                         row["mean_opens"]))
    record = {"timestamp": dt.datetime.now().astimezone().isoformat(),
              "experiment": "P6.3 C5: Table 6 reproduction attempt", "table6": TABLE6,
              "attempt_A_public_entry_point": a, "attempt_B_protocol_from_paper": b, "C5": grade,
              "exploratory_protocols": rows,
              "horizon5_policy_thresholds": {
                  "open_right_when_p_tiger_right_below": max((p for p in np.linspace(0, 0.5, 5001) if h5(p) == OPEN_RIGHT),
                                                             default=None)}}
    print("C5: %s" % grade)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p6_3-table6-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps(record, indent=2, default=float), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
