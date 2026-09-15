# P6.2 - QANTIS POMDP half: closed-loop action sequences (C4), an exact Tiger baseline (Q2) and threshold sensitivity (Q3).
#
# Tiger model: paper §8.2.1 (2 states, 3 actions, 2 observations, gamma = 0.95, listening correct with probability 0.85) with
# the rewards of the public code (tiger_problem.py L37-40, L80-86): listen -1; open the tiger's door -100; open the other +10.
# Opening a door resets the tiger uniformly and gives an uninformative observation. Belief p = P(tiger-right).
#
# C4 (plan): with the one-step planner the paper describes (§8.6: "classical QBRL planner (horizon h = 1) selects the greedy
# action"), exact belief updates and the stated observation sequences, the loops choose
#     T = 4, obs [0,0,0,0]:          listen, listen, open-right, listen
#     T = 8, obs [0,0,0,1,1,1,0,0]:  open-right at t = 2, open-left at t = 5, listen otherwise
# One step of the loop, as in the paper's Table 16/17 and the script: choose the action from the current belief, then update
# with that step's observation (a reset to uniform after an open action). The horizon-1 planner is the argmax of the immediate
# expected reward; the public lookahead tree at horizon 1 computes exactly this value (children are not expanded, so their
# value is 0), and ties go to the lowest action index, as in its best_action().
# Grading, written before the first run: reproduced if the whole sequence matches; not reproduced otherwise; per loop.
#
# Q2 (no grade): exact value iteration on the belief interval (grid of 20,001 points, linear interpolation, until the largest
# change is below 1e-10), the optimal policy's thresholds and value at p = 0.5, against the horizon-1 planner. Simulated
# reward of both policies under two explicit protocols, 100 episodes x 50 steps, seed 42:
#     each episode starts with the tiger placed uniformly and belief 0.5; after an open action the tiger is re-placed uniformly
#     and the belief reset to 0.5; reward summed (a) undiscounted, (b) discounted by gamma^t.
#
# Q3 (no grade): which of the paper's reported hardware Hellinger distances pass at 0.15 but fail at 0.05. Exploratory, after
# the fact: the Hellinger distance recomputed from the posteriors the paper prints, with the effect of their 3-decimal rounding.
#
# Usage:
#     python src/p6_loops.py

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import pathlib

import numpy as np

RESULTS = pathlib.Path(__file__).resolve().parents[1] / "results"
GAMMA = 0.95
ACCURACY = 0.85
LISTEN, OPEN_LEFT, OPEN_RIGHT = 0, 1, 2
NAMES = {LISTEN: "listen", OPEN_LEFT: "open-left", OPEN_RIGHT: "open-right"}
R_LISTEN, R_TIGER, R_TREASURE = -1.0, -100.0, 10.0


def expected_reward(p: np.ndarray | float, action: int):
    """p = P(tiger-right). Open-left is good when the tiger is right."""
    if action == LISTEN:
        return R_LISTEN + 0.0 * np.asarray(p)
    if action == OPEN_LEFT:
        return R_TREASURE * np.asarray(p) + R_TIGER * (1 - np.asarray(p))
    return R_TREASURE * (1 - np.asarray(p)) + R_TIGER * np.asarray(p)


def update(p: float, obs: int, action: int) -> float:
    if action != LISTEN:
        return 0.5
    right = (ACCURACY if obs == 1 else 1 - ACCURACY) * p
    left = (ACCURACY if obs == 0 else 1 - ACCURACY) * (1 - p)
    return right / (right + left)


def greedy_action(p: float) -> int:
    values = [float(expected_reward(p, a)) for a in (LISTEN, OPEN_LEFT, OPEN_RIGHT)]
    return int(max(range(3), key=lambda a: values[a]))           # first maximum wins, as best_action()


LOOPS = {
    "T4": {"obs": [0, 0, 0, 0], "paper_actions": ["listen", "listen", "open-right", "listen"]},
    "T8": {"obs": [0, 0, 0, 1, 1, 1, 0, 0],
           "paper_actions": ["listen", "listen", "open-right", "listen", "listen", "open-left", "listen", "listen"]},
}


def run_loop(obs_sequence: list, policy=greedy_action) -> list:
    p, steps = 0.5, []
    for t, obs in enumerate(obs_sequence):
        action = policy(p)
        posterior = update(p, obs, action)
        steps.append({"t": t, "prior_p_tiger_right": p, "obs": obs, "action": NAMES[action], "posterior_p_tiger_right": posterior})
        p = posterior
    return steps


def c4() -> dict:
    out = {}
    for name, spec in LOOPS.items():
        steps = run_loop(spec["obs"])
        actions = [s["action"] for s in steps]
        out[name] = {"steps": steps, "actions": actions, "paper_actions": spec["paper_actions"],
                     "grade": "reproduced" if actions == spec["paper_actions"] else "not reproduced"}
    return out


# ---------------------------------------------------------------- Q2: exact baseline

def value_iteration(points: int = 20001, tol: float = 1e-10, max_iter: int = 5000) -> dict:
    grid = np.linspace(0.0, 1.0, points)
    V = np.zeros(points)
    p_obs1 = ACCURACY * grid + (1 - ACCURACY) * (1 - grid)                    # P(hear-right | p)
    post = {1: ACCURACY * grid / p_obs1, 0: (1 - ACCURACY) * grid / (1 - p_obs1)}
    for iteration in range(1, max_iter + 1):
        v_half = float(np.interp(0.5, grid, V))
        q_listen = R_LISTEN + GAMMA * (p_obs1 * np.interp(post[1], grid, V) + (1 - p_obs1) * np.interp(post[0], grid, V))
        q_left = expected_reward(grid, OPEN_LEFT) + GAMMA * v_half
        q_right = expected_reward(grid, OPEN_RIGHT) + GAMMA * v_half
        new = np.maximum(q_listen, np.maximum(q_left, q_right))
        change = float(np.max(np.abs(new - V)))
        V = new
        if change < tol:
            break
    Q = np.vstack([q_listen, q_left, q_right])
    policy = np.argmax(Q, axis=0)
    right_open = grid[policy == OPEN_RIGHT]
    left_open = grid[policy == OPEN_LEFT]
    return {"grid": grid, "V": V, "policy": policy, "iterations": iteration, "last_change": change,
            "value_at_0.5": float(np.interp(0.5, grid, V)),
            "open_right_when_p_tiger_right_below": float(right_open.max()) if right_open.size else None,
            "open_left_when_p_tiger_right_above": float(left_open.min()) if left_open.size else None}


def optimal_policy_from(vi: dict):
    grid, policy = vi["grid"], vi["policy"]

    def act(p: float) -> int:
        return int(policy[int(round(p * (len(grid) - 1)))])
    return act


def simulate(policy, episodes: int = 100, steps: int = 50, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    undiscounted, discounted = [], []
    for _ in range(episodes):
        tiger_right = rng.random() < 0.5
        p, total, total_d = 0.5, 0.0, 0.0
        for t in range(steps):
            action = policy(p)
            if action == LISTEN:
                reward = R_LISTEN
                correct = rng.random() < ACCURACY
                obs = int(tiger_right) if correct else int(not tiger_right)
                p = update(p, obs, LISTEN)
            else:
                good = (action == OPEN_LEFT and tiger_right) or (action == OPEN_RIGHT and not tiger_right)
                reward = R_TREASURE if good else R_TIGER
                tiger_right = rng.random() < 0.5
                p = 0.5
            total += reward
            total_d += GAMMA ** t * reward
        undiscounted.append(total)
        discounted.append(total_d)
    return {"undiscounted_mean": float(np.mean(undiscounted)), "undiscounted_sd": float(np.std(undiscounted, ddof=1)),
            "discounted_mean": float(np.mean(discounted)), "discounted_sd": float(np.std(discounted, ddof=1))}


def q2() -> dict:
    vi = value_iteration()
    optimal = optimal_policy_from(vi)
    return {
        "value_iteration": {k: v for k, v in vi.items() if k not in ("grid", "V", "policy")},
        "greedy_thresholds": {"open_right_when_p_tiger_right_below": (R_TREASURE - R_LISTEN) / (R_TREASURE - R_TIGER),
                              "open_left_when_p_tiger_right_above": 1 - (R_TREASURE - R_LISTEN) / (R_TREASURE - R_TIGER)},
        "loops_with_optimal_policy": {name: [s["action"] for s in run_loop(spec["obs"], optimal)] for name, spec in LOOPS.items()},
        "simulation_100x50_seed42": {"greedy_horizon1": simulate(greedy_action), "optimal": simulate(optimal)},
        "grid_points": len(vi["grid"]),
    }


# ---------------------------------------------------------------- Q3: thresholds

PAPER_HELLINGER = [
    ("Grover k = 1 posterior (Table 15)", 0.0015),
    ("Tiger minimal, obs 0 (Table 15)", 0.025),
    ("Tiger minimal, obs 1 (Table 15)", 0.014),
    ("4-state, obs 0 (Table 15)", 0.128),
    ("4-state, obs 1 (Table 15)", 0.044),
    ("Tiger full 11-qubit, raw (§8.6)", 0.235),
    ("Tiger full 11-qubit, ZNE (§8.6)", 0.277),
    ("Tiger minimal ZNE scale 1 (§8.6)", 0.0025),
    ("Tiger minimal ZNE scale 3 (§8.6)", 0.0176),
    ("Tiger minimal ZNE scale 5 (§8.6)", 0.0407),
    ("T = 4 loop, max (Table 16)", 0.0169),
    ("T = 4 replications, max (§8.6)", 0.0148),
    ("T = 8 loop, max (Table 17)", 0.0149),
    ("Table 18 full circuit, ibm_torino raw", 0.231),
    ("Table 18 full circuit, ibm_fez raw", 0.259),
]

# posteriors printed in the paper: (label, prior [left, right] or None for uniform-prior 4-state, obs, action, printed posterior,
# reported Hellinger, exact reference printed by the paper or None)
PRINTED = [
    ("4-state obs 0", None, 0, "listen4", [0.261, 0.418, 0.192, 0.128], 0.128, [0.425, 0.350, 0.150, 0.075]),
    ("4-state obs 1", None, 1, "listen4", [0.065, 0.181, 0.379, 0.375], 0.044, [0.075, 0.150, 0.350, 0.425]),
    ("Grover posterior", None, 1, "given", [0.849, 0.151], 0.0015, [0.851, 0.149]),
    ("T4 t0", [0.500, 0.500], 0, "listen", [0.846, 0.154], 0.0043, None),
    ("T4 t1", [0.846, 0.154], 0, "listen", [0.972, 0.028], 0.0066, None),
    ("T4 t2", [0.972, 0.028], 0, "open", [0.500, 0.500], 0.0003, None),
    ("T4 t3", [0.500, 0.500], 0, "listen", [0.867, 0.133], 0.0169, None),
    ("T8 t0", [0.500, 0.500], 0, "listen", [0.847, 0.153], 0.0031, None),
    ("T8 t1", [0.847, 0.153], 0, "listen", [0.973, 0.027], 0.0091, None),
    ("T8 t2", [0.973, 0.027], 0, "open", [0.518, 0.482], 0.0128, None),
    ("T8 t3", [0.518, 0.482], 1, "listen", [0.175, 0.825], 0.0149, None),
    ("T8 t4", [0.175, 0.825], 1, "listen", [0.043, 0.957], 0.0124, None),
    ("T8 t5", [0.043, 0.957], 1, "open", [0.505, 0.495], 0.0036, None),
    ("T8 t6", [0.505, 0.495], 0, "listen", [0.853, 0.147], 0.0006, None),
    ("T8 t7", [0.853, 0.147], 0, "listen", [0.975, 0.025], 0.0107, None),
]


def hellinger(p, q) -> float:
    return float(math.sqrt(0.5 * np.sum((np.sqrt(np.asarray(p, float)) - np.sqrt(np.asarray(q, float))) ** 2)))


def reference(prior, obs: int, action: str) -> list:
    if action == "open":
        return [0.5, 0.5]
    right = update(prior[1], obs, LISTEN)
    return [1 - right, right]


def rounding_range(posterior, ref_fn, prior) -> tuple[float, float]:
    """Hellinger over the 3-decimal rounding box of a printed 2-state posterior (and its printed prior)."""
    values = []
    for dp, dq in itertools.product((-0.0005, 0.0, 0.0005), repeat=2):
        post = [posterior[0] + dp, 1 - posterior[0] - dp]
        pr = None if prior is None else [prior[0] + dq, 1 - prior[0] - dq]
        values.append(hellinger(post, ref_fn(pr)))
    return min(values), max(values)


def q3() -> dict:
    thresholds = [{"result": label, "hellinger": h, "pass_0.15": h < 0.15, "pass_0.05": h < 0.05,
                   "changes": (h < 0.15) != (h < 0.05)} for label, h in PAPER_HELLINGER]
    recomputed = []
    for label, prior, obs, action, printed, reported, exact in PRINTED:
        if action in ("listen4", "given"):
            h = hellinger(printed, exact)
            row = {"label": label, "reported": reported, "recomputed": h}
        else:
            ref = reference(prior, obs, action)
            lo, hi = rounding_range(printed, lambda pr: reference(pr, obs, action), prior)
            row = {"label": label, "reported": reported, "reference_posterior": ref,
                   "recomputed": hellinger(printed, ref), "range_over_rounding": [lo, hi],
                   "reported_within_rounding_range": lo - 1e-12 <= reported <= hi + 1e-12}
        recomputed.append(row)
    return {"thresholds": thresholds, "change_grade": [t["result"] for t in thresholds if t["changes"]],
            "exploratory_recomputed_from_printed_posteriors": recomputed}


def main() -> None:
    record = {"timestamp": dt.datetime.now().astimezone().isoformat(),
              "experiment": "P6.2 QANTIS POMDP half: C4 loops, Q2 exact Tiger baseline, Q3 thresholds",
              "model": {"gamma": GAMMA, "listen_accuracy": ACCURACY,
                        "rewards": {"listen": R_LISTEN, "tiger": R_TIGER, "treasure": R_TREASURE}},
              "C4": c4(), "Q2": q2(), "Q3": q3()}
    print("C4: %s" % {k: v["grade"] for k, v in record["C4"].items()})
    print(json.dumps({k: record[k] for k in ("Q2", "Q3")}, indent=1))
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p6_2-loops-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
