# Tests for P2.3. Each check uses a route that does not depend on the code being tested:
#   - L(u) is compared with an integer program of the relaxed problem, built and solved separately with HiGHS
#   - the bounds are checked against the exact ILP optimum and its LP relaxation
#   - every answer is re-checked as a partition and re-costed from the tuple table
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import dataclasses
import math
import pathlib
import sys
import unittest

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p2_heuristics import (  # noqa: E402
    anneal_study,
    greedy,
    lagrangian_relaxation,
    lagrangian_value,
    lr_structure,
    recover,
)
from p2_ilp import lp_relaxation, solve_ilp  # noqa: E402
from p2_scene import PURE, Params, build_tuples, generate, is_partition, partition_cost  # noqa: E402


def relaxed_by_milp(scene, ts, u):
    """min sum (c_k - u_{i3}) x_k + sum u, with only the sensor-1 and sensor-2 constraints, as a separate integer program."""
    rows = [(s, j + 1) for s in (0, 1) for j in range(len(scene.measurements[s]))]
    if not ts.tuples:
        return float(np.sum(u[1:]))
    c = np.array([cost - (u[t[2]] if t[2] > 0 else 0.0) for t, cost in zip(ts.tuples, ts.costs)])
    if not rows:
        return float(np.sum(u[1:]) + np.minimum(c, 0).sum())
    A = np.array([[1.0 if t[s] == j else 0.0 for t in ts.tuples] for s, j in rows])
    result = milp(c=c, constraints=LinearConstraint(A, 1, 1), integrality=np.ones(len(c)), bounds=Bounds(0, 1),
                  options={"mip_rel_gap": 0})
    return float(result.fun) + float(np.sum(u[1:]))


class TestLagrangian(unittest.TestCase):
    def test_value_matches_separate_integer_program(self):
        rng = np.random.default_rng(50)
        params = Params()
        checked = 0
        for T in (1, 2, 3, 4):
            for _ in range(15):
                scene = generate(T, params, rng)
                ts = build_tuples(scene, params)
                u = np.concatenate([[0.0], rng.normal(0, 5, len(scene.measurements[2]))])
                value, chosen = lagrangian_value(scene, ts, u)
                self.assertIsNotNone(chosen)
                self.assertAlmostEqual(value, relaxed_by_milp(scene, ts, u), places=6)
                checked += 1
        self.assertEqual(checked, 60)

    def test_bounds_sandwich_the_optimum(self):
        rng = np.random.default_rng(51)
        params = Params()
        for T in (2, 3, 4, 5):
            for _ in range(10):
                scene = generate(T, params, rng)
                ts = build_tuples(scene, params)
                optimum = solve_ilp(scene, ts)["cost"]
                lp = lp_relaxation(scene, ts)["bound"]
                lr = lagrangian_relaxation(scene, ts)
                tol = 1e-6 * max(1.0, abs(optimum))
                self.assertLessEqual(lp, optimum + tol)
                self.assertLessEqual(lr["lower_bound"], lp + tol)
                self.assertGreaterEqual(lr["upper_bound"], optimum - tol)
                self.assertTrue(is_partition(scene, lr["partition"]))
                self.assertAlmostEqual(partition_cost(ts, lr["partition"]), lr["upper_bound"], places=9)
                if lr["certified"]:
                    self.assertAlmostEqual(lr["upper_bound"], optimum, delta=2 * tol)

    def test_recovery_from_zero_multipliers_is_a_partition(self):
        rng = np.random.default_rng(52)
        params = Params()
        for _ in range(30):
            scene = generate(4, params, rng)
            ts = build_tuples(scene, params)
            structure = lr_structure(ts)
            _, chosen = lagrangian_value(scene, ts, np.zeros(len(scene.measurements[2]) + 1), structure)
            cost, partition = recover(scene, ts, chosen, structure[0])
            self.assertTrue(is_partition(scene, partition))
            self.assertAlmostEqual(cost, partition_cost(ts, partition), places=9)


class TestGreedyAndAnnealing(unittest.TestCase):
    def test_greedy_is_a_partition_never_below_the_optimum(self):
        rng = np.random.default_rng(53)
        params = Params()
        for T in (2, 4, 6):
            for _ in range(15):
                scene = generate(T, params, rng)
                ts = build_tuples(scene, params)
                result = greedy(scene, ts)
                self.assertTrue(result["feasible"])
                self.assertGreaterEqual(result["cost"], solve_ilp(scene, ts)["cost"] - 1e-6)

    def test_greedy_solves_well_separated_low_noise_scenes(self):
        rng = np.random.default_rng(54)
        params = dataclasses.replace(Params(), **PURE, sigma_range=0.1, sigma_bearing=1e-4, spacing=500.0)
        for _ in range(10):
            scene = generate(3, params, rng)
            ts = build_tuples(scene, params)
            self.assertAlmostEqual(greedy(scene, ts)["cost"], solve_ilp(scene, ts)["cost"], places=6)

    def test_annealing_finds_the_optimum_of_pure_two_target_scenes(self):
        rng = np.random.default_rng(55)
        params = dataclasses.replace(Params(), **PURE)
        for _ in range(10):
            scene = generate(2, params, rng)
            ts = build_tuples(scene, params)
            result = anneal_study(scene, ts, solve_ilp(scene, ts)["cost"], restarts=32, sweeps=100, rng=rng)
            self.assertTrue(result["best_of_restarts_optimal"])
            self.assertTrue(math.isclose(result["penalty"], max(float(np.max(np.abs(ts.costs))), 1.0)))


if __name__ == "__main__":
    unittest.main()
