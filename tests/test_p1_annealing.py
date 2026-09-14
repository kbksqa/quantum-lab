# Tests for P1.3.
#   - the rebuilt P1.2 instance sets must reproduce the median safe/critical ratios stored in the committed
#     P1.2 result file (a fingerprint computed without any annealing)
#   - a hand-built instance with A_crit = 0 must be solved correctly by any positive penalty
#   - the scoring of annealing states is checked on hand-built states
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import json
import pathlib
import sys
import unittest

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p1_annealing import max_abs_rule, p1_2_instances, score  # noqa: E402
from p1_penalty import critical_penalty, enumerate_strings  # noqa: E402
from p1_qubo import brute_force_minimum, build_qubo, decode, hungarian_cost, safe_penalty  # noqa: E402


class TestReplay(unittest.TestCase):
    def test_rebuilt_instances_match_p1_2_fingerprint(self):
        stored = json.loads((ROOT / "results" / "p1_2-penalty-20260914-125028.json").read_text(encoding="utf-8"))
        sets = p1_2_instances()
        for name, matrices in sets.items():
            self.assertEqual(len(matrices), 50)
            ratios = []
            for C in matrices:
                strings = enumerate_strings(C)
                a_crit = critical_penalty(strings, hungarian_cost(C))
                base = a_crit if a_crit > 0 else 1e-6
                ratios.append(safe_penalty(strings["costs"]) / base)
            self.assertAlmostEqual(float(np.median(ratios)), stored["summary"][name]["median_safe_over_crit"], places=9)


class TestZeroCriticalPenalty(unittest.TestCase):
    def test_any_positive_penalty_is_enough(self):
        C = np.array([[-5.0, np.inf], [np.inf, -5.0]])
        optimum = hungarian_cost(C)
        self.assertEqual(critical_penalty(enumerate_strings(C), optimum), 0.0)
        qubo = build_qubo(C, penalty=1e-3)
        e_min, x = brute_force_minimum(qubo)
        feasible, _ = decode(x, qubo)
        self.assertTrue(feasible)
        self.assertAlmostEqual(e_min, optimum, delta=1e-9)

    def test_max_abs_rule_ignores_forbidden_cells(self):
        C = np.array([[1.0, -7.0], [np.inf, 3.0]])
        self.assertEqual(max_abs_rule(C), 7.0)


class TestScore(unittest.TestCase):
    def test_score_on_hand_built_states(self):
        C = np.array([[1.0, 5.0], [5.0, 1.0]])
        qubo = build_qubo(C, penalty=10.0)
        order = {v: k for k, v in enumerate(qubo["variables"])}

        def state(cells):
            x = np.zeros(len(qubo["variables"]), dtype=int)
            for cell in cells:
                x[order[cell]] = 1
            return x

        states = np.array([
            state([(0, 0), (1, 1)]),   # optimal, cost 2
            state([(0, 1), (1, 0)]),   # feasible, cost 10
            state([(0, 0)]),           # infeasible
            state([(0, 0), (1, 1)]),   # optimal again
        ])
        result = score(states, qubo, hungarian_cost(C))
        self.assertAlmostEqual(result["success"], 0.5)
        self.assertAlmostEqual(result["feasible_share"], 0.75)
        self.assertTrue(result["best_of_restarts_optimal"])
        self.assertAlmostEqual(result["best_gap_over_spread"], 0.0)


if __name__ == "__main__":
    unittest.main()
