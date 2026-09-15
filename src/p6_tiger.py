# P6.1 - QANTIS POMDP half rebuilt from the paper: Tiger belief circuits and one Grover iterate, with claims C1, C2, C6, C7 and
# question Q1 of docs/p6-plan.md, on a noiseless statevector.
#
# Model (paper §8.2.1, §8.6): state 0 = tiger-left, 1 = tiger-right; observation 0 = hear-left, 1 = hear-right; listening is
# correct with probability 0.85. Opening a door resets the tiger uniformly and gives an uninformative observation.
#
# Circuits, as the paper describes them (§8.6). Qubit order is Qiskit's: basis index = sum_k x_k 2^k.
#   2-state: q0 = state, q1 = observation, index = s + 2 o.
#     A = RY(2 arccos sqrt(b0)) on q0, then for each state s an RY on q1 controlled on q0 = s, with P(obs = 0 | s) = cos^2(t_s/2).
#     A|00> = sum_{s,o} sqrt(b(s) O(o|s)) |s, o>.
#     Open-door actions: H on both qubits ("Hadamard-only preparation").
#   Grover step: G = A S0 A^dagger S_f applied after A. S_f phase-flips obs = target, S0 = X0 X1 CZ X0 X1.
#   4-state: q0, q1 = state (s = q0 + 2 q1), q2 = observation. UCRy prior on q1 then q0, then one doubly controlled RY per state.
# Independent reference for every circuit: the amplitude vector written down directly, and A S0 A^dagger = I - 2|psi><psi|,
# which holds for any A with A|00> = |psi>.
# Hellinger distance as in the paper's code: sqrt(1/2 sum (sqrt p - sqrt q)^2). Total variation: 1/2 sum |p - q|.
#
# Grading rules, written here before the first run (the plan fixes the claims; these make them operational):
#   C1  paper values 0.171, 0.917 and posterior [0.851, 0.149]. Reproduced if every value is matched within 0.0005 (the
#       paper's rounding); partly reproduced if every value is within 0.005; not reproduced otherwise. The stated amplification
#       5.4x is reported, not graded.
#   C2  the post-selected posterior equals exact Bayes (Hellinger distance < 1e-9) for every prior tested, both observations,
#       listen and open actions, 2-state and 4-state: reproduced; otherwise not reproduced.
#   C6  Table 21 (P(e) = 0.05): reproduced if the amplified P(e) for G = 0..5 all equal sin^2((2G + 1) theta) within 0.0005;
#       partly reproduced if G = 0 and G = 3 match but not all; not reproduced otherwise. The paper's three iteration
#       formulas are evaluated and reported.
#   C7  "Hellinger < 0.15 <=> <= 1.1% total-variation distance". Every pair satisfies H^2 <= TV <= H sqrt(2 - H^2). Reproduced
#       if no pair with H < 0.15 has TV > 0.011; not reproduced if one exists, shown by the bound and an explicit example.
#   Q1  usable posterior samples per application of the belief oracle (A and A^dagger each count once) for the direct
#       circuit, the Grover k = 1 circuit and classical rejection sampling, from theory and from the paper's hardware values.
#
# Usage:
#     python src/p6_tiger.py

from __future__ import annotations

import datetime as dt
import json
import math
import pathlib

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import RYGate
from qiskit.quantum_info import Statevector

RESULTS = pathlib.Path(__file__).resolve().parents[1] / "results"
LISTEN_ACCURACY = 0.85
P_OBS0_2 = np.array([LISTEN_ACCURACY, 1 - LISTEN_ACCURACY])      # P(hear-left | s)
P_OBS0_4 = np.array([0.85, 0.70, 0.30, 0.15])                    # 4-state Corridor Tiger, §8.6
LISTEN, OPEN_LEFT, OPEN_RIGHT = 0, 1, 2

PAPER = {
    "C1": {"p_obs1_baseline": 0.171, "p_obs1_grover": 0.917, "posterior": [0.851, 0.149], "amplification": 5.4,
           "hardware_p_obs1_baseline": 0.179, "hardware_p_obs1_grover": 0.907, "hardware_counts_grover_obs1": 7429,
           "hardware_counts_baseline_obs1": 1463, "shots": 8192},
    "C6_table21": {"p_e": 0.05, "amplified": [0.050, 0.192, 0.485, 0.912, 0.721, 0.298]},
    "C7": {"hellinger": 0.15, "total_variation": 0.011},
    "four_state_classical_posteriors": {"0": [0.425, 0.350, 0.150, 0.075], "1": [0.075, 0.150, 0.350, 0.425]},
}


# ---------------------------------------------------------------- exact references

def likelihood(p_obs0: np.ndarray, obs: int) -> np.ndarray:
    return p_obs0 if obs == 0 else 1.0 - p_obs0


def bayes(prior, p_obs0: np.ndarray, obs: int, action: int = LISTEN) -> tuple[np.ndarray, float]:
    prior = np.asarray(prior, dtype=float)
    if action != LISTEN:
        return np.full(len(prior), 1.0 / len(prior)), 0.5
    joint = prior * likelihood(p_obs0, obs)
    return joint / joint.sum(), float(joint.sum())


def oracle_amplitudes(prior, p_obs0: np.ndarray) -> np.ndarray:
    """sum_{s,o} sqrt(b(s) O(o|s)) |s, o>, index = s + n_states * o."""
    prior = np.asarray(prior, dtype=float)
    return np.concatenate([np.sqrt(prior * p_obs0), np.sqrt(prior * (1.0 - p_obs0))]).astype(complex)


def grover_reference(prior, p_obs0: np.ndarray, target: int) -> np.ndarray:
    psi = oracle_amplitudes(prior, p_obs0)
    n = len(prior)
    flipped = psi.copy()
    flipped[n * target: n * (target + 1)] *= -1
    return flipped - 2.0 * psi * np.vdot(psi, flipped)


def hellinger(p, q) -> float:
    return float(math.sqrt(0.5 * np.sum((np.sqrt(np.asarray(p, float)) - np.sqrt(np.asarray(q, float))) ** 2)))


def total_variation(p, q) -> float:
    return float(0.5 * np.sum(np.abs(np.asarray(p, float) - np.asarray(q, float))))


def post_select(probs: np.ndarray, n_states: int, obs: int) -> tuple[np.ndarray, float]:
    joint = probs.reshape(2, n_states)[obs]
    return joint / joint.sum(), float(joint.sum())


# ---------------------------------------------------------------- circuits

def angle(p0: float) -> float:
    return 2.0 * math.acos(math.sqrt(min(max(p0, 0.0), 1.0)))


def oracle_circuit(prior, p_obs0: np.ndarray = P_OBS0_2) -> QuantumCircuit:
    qc = QuantumCircuit(2, name="A")
    qc.ry(angle(prior[0]), 0)
    for s in (0, 1):
        qc.append(RYGate(angle(p_obs0[s])).control(1, ctrl_state=s, annotated=False), [0, 1])
    return qc


def tiger_circuit(prior, action: int, p_obs0: np.ndarray = P_OBS0_2) -> QuantumCircuit:
    if action == LISTEN:
        return oracle_circuit(prior, p_obs0)
    qc = QuantumCircuit(2, name="open")
    qc.h(0)
    qc.h(1)
    return qc


def grover1_circuit(prior, target: int, p_obs0: np.ndarray = P_OBS0_2) -> QuantumCircuit:
    A = oracle_circuit(prior, p_obs0)
    qc = QuantumCircuit(2, name="grover1")
    qc.compose(A, inplace=True)
    if target == 1:
        qc.z(1)
    else:
        qc.x(1)
        qc.z(1)
        qc.x(1)
    qc.compose(A.inverse(), inplace=True)
    qc.x([0, 1])
    qc.cz(0, 1)
    qc.x([0, 1])
    qc.compose(A, inplace=True)
    return qc


def four_state_circuit(prior4, p_obs0: np.ndarray = P_OBS0_4) -> QuantumCircuit:
    p = np.asarray(prior4, dtype=float)
    qc = QuantumCircuit(3, name="tiger4")
    low = p[0] + p[1]
    qc.ry(angle(low), 1)                                                        # q1 = 0 <=> s in {0, 1}
    qc.append(RYGate(angle(p[0] / low)).control(1, ctrl_state=0, annotated=False), [1, 0])
    qc.append(RYGate(angle(p[2] / (1 - low))).control(1, ctrl_state=1, annotated=False), [1, 0])
    for s in range(4):
        qc.append(RYGate(angle(p_obs0[s])).control(2, ctrl_state=s, annotated=False), [0, 1, 2])
    return qc


def statevector(qc: QuantumCircuit) -> np.ndarray:
    return Statevector(qc).data


def phase_aligned_difference(reference: np.ndarray, other: np.ndarray) -> float:
    overlap = np.vdot(other, reference)
    phase = overlap / abs(overlap) if abs(overlap) > 0 else 1.0
    return float(np.max(np.abs(reference - other * phase)))


# ---------------------------------------------------------------- claims

def c1() -> dict:
    prior, target = [0.97, 0.03], 1
    base_state = statevector(oracle_circuit(prior))
    grover_state = statevector(grover1_circuit(prior, target))
    base_p = float(np.sum(np.abs(base_state.reshape(2, 2)[target]) ** 2))
    grover_p = float(np.sum(np.abs(grover_state.reshape(2, 2)[target]) ** 2))
    posterior, _ = post_select(np.abs(grover_state) ** 2, 2, target)
    exact_posterior, evidence = bayes(prior, P_OBS0_2, target)
    theta = math.asin(math.sqrt(evidence))
    ours = {"p_obs1_baseline": base_p, "p_obs1_grover": grover_p, "posterior": posterior.tolist(),
            "amplification": grover_p / base_p}
    paper = PAPER["C1"]
    differences = [abs(base_p - paper["p_obs1_baseline"]), abs(grover_p - paper["p_obs1_grover"]),
                   abs(posterior[0] - paper["posterior"][0]), abs(posterior[1] - paper["posterior"][1])]
    grade = ("reproduced" if max(differences) <= 0.0005 else
             "partly reproduced" if max(differences) <= 0.005 else "not reproduced")
    return {
        "ours": ours, "paper": {k: paper[k] for k in ("p_obs1_baseline", "p_obs1_grover", "posterior", "amplification")},
        "max_difference": max(differences), "grade": grade,
        "checks": {
            "baseline_circuit_vs_direct_amplitudes": phase_aligned_difference(oracle_amplitudes(prior, P_OBS0_2), base_state),
            "grover_circuit_vs_reflection_formula": phase_aligned_difference(grover_reference(prior, P_OBS0_2, target),
                                                                              grover_state),
            "grover_p_vs_sin2_3theta": abs(grover_p - math.sin(3 * theta) ** 2),
            "posterior_vs_exact_bayes_hellinger": hellinger(posterior, exact_posterior),
            "exact_bayes_evidence": evidence, "exact_bayes_posterior": exact_posterior.tolist(),
            "hardware_count_ratios": {"grover": paper["hardware_counts_grover_obs1"] / paper["shots"],
                                      "baseline": paper["hardware_counts_baseline_obs1"] / paper["shots"],
                                      "ratio": paper["hardware_counts_grover_obs1"] / paper["hardware_counts_baseline_obs1"]},
        },
    }


C2_PRIORS_2 = [0.5, 0.97, 0.03, 0.846, 0.154, 0.972, 0.028, 0.867, 0.133, 0.518, 0.482, 0.175, 0.825, 0.043, 0.957, 0.505,
               0.495, 0.853, 0.147, 0.975, 0.025]                           # P(tiger-left): values that appear in §8.6


def c2(seed: int = 2061, random_priors: int = 20) -> dict:
    rng = np.random.default_rng(seed)
    priors2 = [[b, 1 - b] for b in C2_PRIORS_2] + [list(rng.dirichlet([1, 1])) for _ in range(random_priors)]
    worst2 = {"listen": 0.0, "open": 0.0}
    worst_state2 = 0.0
    for prior in priors2:
        for action, key in ((LISTEN, "listen"), (OPEN_RIGHT, "open")):
            state = statevector(tiger_circuit(prior, action))
            if action == LISTEN:
                worst_state2 = max(worst_state2, phase_aligned_difference(oracle_amplitudes(prior, P_OBS0_2), state))
            for obs in (0, 1):
                posterior, _ = post_select(np.abs(state) ** 2, 2, obs)
                worst2[key] = max(worst2[key], hellinger(posterior, bayes(prior, P_OBS0_2, obs, action)[0]))
    priors4 = [[0.25] * 4] + [list(rng.dirichlet([1, 1, 1, 1])) for _ in range(random_priors)]
    worst4, worst_state4 = 0.0, 0.0
    uniform_posteriors = {}
    for i, prior in enumerate(priors4):
        state = statevector(four_state_circuit(prior))
        worst_state4 = max(worst_state4, phase_aligned_difference(oracle_amplitudes(prior, P_OBS0_4), state))
        for obs in (0, 1):
            posterior, _ = post_select(np.abs(state) ** 2, 4, obs)
            worst4 = max(worst4, hellinger(posterior, bayes(prior, P_OBS0_4, obs)[0]))
            if i == 0:
                uniform_posteriors[str(obs)] = posterior.tolist()
    worst = max(worst2["listen"], worst2["open"], worst4)
    paper_posteriors = PAPER["four_state_classical_posteriors"]
    return {
        "priors_2_state": len(priors2), "priors_4_state": len(priors4),
        "max_hellinger_2_state": worst2, "max_hellinger_4_state": worst4,
        "max_circuit_vs_direct_amplitudes": {"2_state": worst_state2, "4_state": worst_state4},
        "four_state_uniform_prior_posteriors": uniform_posteriors,
        "paper_classical_posteriors_match": {obs: float(np.max(np.abs(np.array(uniform_posteriors[obs]) - np.array(v))))
                                             for obs, v in paper_posteriors.items()},
        "grade": "reproduced" if worst < 1e-9 else "not reproduced",
    }


def c6() -> dict:
    table = PAPER["C6_table21"]
    theta = math.asin(math.sqrt(table["p_e"]))
    formula = [math.sin((2 * g + 1) * theta) ** 2 for g in range(6)]
    differences = [abs(a - b) for a, b in zip(formula, table["amplified"])]
    if max(differences) <= 0.0005:
        grade = "reproduced"
    elif differences[0] <= 0.0005 and differences[3] <= 0.0005:
        grade = "partly reproduced"
    else:
        grade = "not reproduced"
    return {
        "theta": theta, "formula": formula, "table": table["amplified"], "differences": differences, "grade": grade,
        "iteration_formulas": {
            "section_5_2_floor(pi/(4 theta) - 1/2)": math.floor(math.pi / (4 * theta) - 0.5),
            "table_21_caption_floor(pi/4 sqrt(1/P(e)))": math.floor(math.pi / 4 * math.sqrt(1 / table["p_e"])),
            "table_21_text_floor(pi/(4 theta))": math.floor(math.pi / (4 * theta)),
            "best_G_in_0..5_by_formula": int(np.argmax(formula)),
        },
    }


def c7() -> dict:
    H, limit = PAPER["C7"]["hellinger"], PAPER["C7"]["total_variation"]
    lo, hi = 0.0, 0.5
    target = 0.1499
    for _ in range(200):                                    # [0.5, 0.5] against [0.5 + d, 0.5 - d] with Hellinger = 0.1499
        mid = (lo + hi) / 2
        if hellinger([0.5, 0.5], [0.5 + mid, 0.5 - mid]) < target:
            lo = mid
        else:
            hi = mid
    example_q = [0.5 + lo, 0.5 - lo]
    lo2, hi2 = 0.0, 1.0
    for _ in range(200):                                    # largest H with H sqrt(2 - H^2) <= limit
        mid = (lo2 + hi2) / 2
        if mid * math.sqrt(2 - mid * mid) <= limit:
            lo2 = mid
        else:
            hi2 = mid
    example = {"p": [0.5, 0.5], "q": example_q, "hellinger": hellinger([0.5, 0.5], example_q),
               "total_variation": total_variation([0.5, 0.5], example_q)}
    exists = example["hellinger"] < H and example["total_variation"] > limit
    return {
        "bounds_at_H_0.15": {"tv_lower_H2": H * H, "tv_upper_H_sqrt(2-H2)": H * math.sqrt(2 - H * H)},
        "example": example,
        "hellinger_above_which_tv_must_exceed_1.1%": math.sqrt(limit),
        "hellinger_below_which_tv_is_guaranteed_at_most_1.1%": lo2,
        "grade": "not reproduced" if exists else "reproduced",
    }


def q1() -> dict:
    theory = c1()["ours"]
    paper = PAPER["C1"]
    applications = {"direct": 1, "grover_k1": 3, "classical_rejection": 1}

    def per_call(p_base, p_grover):
        rows = {"direct": p_base / applications["direct"], "grover_k1": p_grover / applications["grover_k1"],
                "classical_rejection": p_base / applications["classical_rejection"]}
        rows["grover_over_direct_per_call"] = rows["grover_k1"] / rows["direct"]
        rows["grover_over_direct_per_shot"] = p_grover / p_base
        return rows

    return {"oracle_applications_per_shot": applications,
            "theory": per_call(theory["p_obs1_baseline"], theory["p_obs1_grover"]),
            "paper_hardware": per_call(paper["hardware_p_obs1_baseline"], paper["hardware_p_obs1_grover"])}


def main() -> None:
    record = {"timestamp": dt.datetime.now().astimezone().isoformat(),
              "experiment": "P6.1 QANTIS POMDP half: C1, C2, C6, C7 and Q1 on a noiseless statevector",
              "C1": c1(), "C2": c2(), "C6": c6(), "C7": c7(), "Q1": q1()}
    for key in ("C1", "C2", "C6", "C7"):
        print("%s: %s" % (key, record[key]["grade"]))
    print(json.dumps({k: v for k, v in record.items() if k != "timestamp"}, indent=1))
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p6_1-tiger-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
