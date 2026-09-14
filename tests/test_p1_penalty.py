# Tests for P1.2.
#   - the critical penalty from the enumeration formula is checked against brute-force QUBO minimisation
#     just above and just below the threshold
#   - energies from cost + A * V are checked against the QUBO matrix energy on every bit string
#   - annealing is checked for determinism and for finding the optimum of a tiny instance
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import pathlib
import sys
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p1_penalty import anneal, critical_penalty, enumerate_strings, landscape, score_states  # noqa: E402
from p1_qubo import brute_force_minimum, build_qubo, decode, energy, hungarian_cost  # noqa: E402


class TestCriticalPenalty(unittest.TestCase):
    def test_threshold_is_exact(self):
        rng = np.random.default_rng(31)
        below_checked = 0
        for _ in range(30):
            C = rng.normal(0, 5, size=(3, 3))
            optimum = hungarian_cost(C)
            a_crit = critical_penalty(enumerate_strings(C), optimum)

            above = build_qubo(C, penalty=a_crit * (1 + 1e-6) + 1e-9)
            e_min, x = brute_force_minimum(above)
            feasible, _ = decode(x, above)
            self.assertTrue(feasible)
            self.assertAlmostEqual(e_min, optimum, delta=1e-6)

            if a_crit > 1e-3:
                below = build_qubo(C, penalty=a_crit * (1 - 1e-3))
                e_min, x = brute_force_minimum(below)
                feasible, _ = decode(x, below)
                self.assertLess(e_min, optimum - 1e-9)
                self.assertFalse(feasible)
                below_checked += 1
        self.assertGreater(below_checked, 10)


class TestLandscape(unittest.TestCase):
    def test_energies_match_qubo_matrix(self):
        rng = np.random.default_rng(32)
        for _ in range(10):
            C = rng.normal(0, 5, size=(3, 3))
            A = float(rng.uniform(1, 40))
            strings = enumerate_strings(C)
            from_formula = strings["cost"] + A * strings["V"]
            from_matrix = energy(build_qubo(C, penalty=A), strings["X"])
            self.assertTrue(np.allclose(from_formula, from_matrix, atol=1e-7))

    def test_gap_is_between_zero_and_one(self):
        rng = np.random.default_rng(33)
        C = rng.normal(0, 5, size=(3, 3))
        strings = enumerate_strings(C)
        a_crit = critical_penalty(strings, hungarian_cost(C))
        for s in (1.1, 2, 10):
            gap = landscape(strings, s * max(a_crit, 1e-6))["normalised_gap"]
            self.assertGreater(gap, 0.0)
            self.assertLessEqual(gap, 1.0)


class TestAnnealing(unittest.TestCase):
    def test_deterministic_and_solves_tiny_instance(self):
        rng = np.random.default_rng(34)
        C = rng.uniform(1, 10, size=(2, 2))
        optimum = hungarian_cost(C)
        a_crit = critical_penalty(enumerate_strings(C), optimum)
        qubo = build_qubo(C, penalty=2 * a_crit)
        first = anneal(qubo, restarts=64, sweeps=100, rng=np.random.default_rng(7))
        second = anneal(qubo, restarts=64, sweeps=100, rng=np.random.default_rng(7))
        self.assertTrue(np.array_equal(first, second))
        self.assertGreaterEqual(score_states(first, qubo, optimum)["success"], 0.5)


if __name__ == "__main__":
    unittest.main()
