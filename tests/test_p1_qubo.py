# Tests for P1.1. The QUBO is checked against quantities computed without the QUBO:
#   - on a valid permutation the energy must equal the plain assignment cost
#   - on any bit string, energy - cost must equal A times the squared constraint violation
#   - the brute-force QUBO minimum must equal the Hungarian optimum
#   - pruning the augmented matrix must not change the Hungarian optimum
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import dataclasses
import itertools
import pathlib
import sys
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p1_qubo import (  # noqa: E402
    brute_force_minimum,
    build_qubo,
    check_instance,
    decode,
    energy,
    hungarian_cost,
    prune_augmented,
    safe_penalty,
)
from p1_scenario import Params, augmented_cost, generate, pure_cost  # noqa: E402


def one_hot(qubo, assignment):
    x = np.zeros(len(qubo["variables"]), dtype=int)
    for k, (i, j) in enumerate(qubo["variables"]):
        if assignment[i] == j:
            x[k] = 1
    return x


class TestAlgebra(unittest.TestCase):
    def test_feasible_energy_equals_cost(self):
        rng = np.random.default_rng(21)
        for _ in range(20):
            C = rng.normal(0, 5, size=(3, 3))
            qubo = build_qubo(C)
            for perm in itertools.permutations(range(3)):
                x = one_hot(qubo, perm)
                expected = sum(C[i, perm[i]] for i in range(3))
                self.assertAlmostEqual(float(energy(qubo, x)[0]), expected, delta=1e-9)

    def test_penalty_equals_squared_violation(self):
        rng = np.random.default_rng(22)
        for _ in range(200):
            n = int(rng.integers(2, 5))
            C = rng.normal(0, 5, size=(n, n))
            qubo = build_qubo(C, penalty=float(rng.uniform(0.5, 50)))
            x = rng.integers(0, 2, size=len(qubo["variables"]))
            cost = sum(C[i, j] for bit, (i, j) in zip(x, qubo["variables"]) if bit)
            rows = np.zeros(n)
            cols = np.zeros(n)
            for bit, (i, j) in zip(x, qubo["variables"]):
                rows[i] += bit
                cols[j] += bit
            violation = float(((rows - 1) ** 2).sum() + ((cols - 1) ** 2).sum())
            self.assertAlmostEqual(float(energy(qubo, x)[0]) - cost, qubo["penalty"] * violation, delta=1e-7)

    def test_default_penalty_rule(self):
        C = np.array([[1.0, -2.0], [3.0, np.inf]])
        qubo = build_qubo(C)
        self.assertEqual(len(qubo["variables"]), 3)
        self.assertAlmostEqual(qubo["penalty"], safe_penalty(np.array([1.0, -2.0, 3.0])))
        self.assertAlmostEqual(qubo["penalty"], 2 * 6.0 + 1)


class TestGate(unittest.TestCase):
    def test_pruning_keeps_the_optimum(self):
        rng = np.random.default_rng(23)
        params = Params()
        for n_targets in (1, 2, 3, 4):
            for _ in range(50):
                scene = generate(n_targets, params, rng)
                C, info = augmented_cost(scene, params)
                P = prune_augmented(C, info["tracks"], info["measurements"])
                self.assertAlmostEqual(hungarian_cost(P), hungarian_cost(C), delta=1e-9)
                self.assertLessEqual(int(np.isfinite(P).sum()), int(np.isfinite(C).sum()))

    def test_qubo_minimum_equals_hungarian(self):
        rng = np.random.default_rng(24)
        base = Params()
        pure = dataclasses.replace(base, p_detect=1.0, clutter_per_scan=0.0, gate=None)
        tested = 0
        for _ in range(30):
            for C in (pure_cost(generate(2, pure, rng)), pure_cost(generate(3, pure, rng))):
                record = check_instance(C, max_vars=16)
                self.assertEqual(record["status"], "pass", record)
                tested += 1
            for n_targets in (1, 2):
                scene = generate(n_targets, base, rng)
                C, info = augmented_cost(scene, base)
                record = check_instance(prune_augmented(C, info["tracks"], info["measurements"]), max_vars=16)
                if record["status"] != "skipped":
                    self.assertEqual(record["status"], "pass", record)
                    tested += 1
        self.assertGreater(tested, 80)

    def test_argmin_decodes_to_hungarian_assignment_cost(self):
        rng = np.random.default_rng(25)
        for _ in range(20):
            C = rng.normal(0, 5, size=(3, 3))
            qubo = build_qubo(C)
            _, x = brute_force_minimum(qubo)
            feasible, perm = decode(x, qubo)
            self.assertTrue(feasible)
            self.assertAlmostEqual(sum(C[i, perm[i]] for i in range(3)), hungarian_cost(C), delta=1e-9)


if __name__ == "__main__":
    unittest.main()
