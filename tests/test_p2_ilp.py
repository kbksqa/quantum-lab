# Tests for P2.1. Each check uses a route that does not depend on the code being tested:
#   - the ILP optimum is compared with exact-cover enumeration of every partition (no cost-based pruning)
#   - in pure mode both are compared with a direct loop over permutations, and the partition count with T!^(S-1)
#   - the ILP answer is re-checked as a partition and re-costed from the tuple table
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import dataclasses
import itertools
import math
import pathlib
import sys
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p2_ilp import MODES, difference_modes, enumerate_partitions, solve_ilp, wilson  # noqa: E402
from p2_scene import PURE, Params, build_tuples, generate, is_partition, partition_cost, truth_partition  # noqa: E402


class TestIlpAgainstEnumeration(unittest.TestCase):
    def test_equals_exact_cover_on_tiny_scenes(self):
        rng = np.random.default_rng(30)
        params = Params()
        checked = 0
        for T in (1, 2, 3):
            for _ in range(40):
                scene = generate(T, params, rng)
                ts = build_tuples(scene, params)
                ilp = solve_ilp(scene, ts)
                brute = enumerate_partitions(scene, ts, limit=200_000)
                if brute is None:
                    continue
                self.assertAlmostEqual(ilp["cost"], brute["cost"], places=6)
                checked += 1
        self.assertGreater(checked, 100)

    def test_pure_mode_equals_permutation_loop(self):
        rng = np.random.default_rng(31)
        params = dataclasses.replace(Params(), **PURE)
        for T in (2, 3):
            for _ in range(10):
                scene = generate(T, params, rng)
                ts = build_tuples(scene, params)
                best = min(partition_cost(ts, [(i + 1, p2[i] + 1, p3[i] + 1) for i in range(T)])
                           for p2 in itertools.permutations(range(T)) for p3 in itertools.permutations(range(T)))
                self.assertAlmostEqual(solve_ilp(scene, ts)["cost"], best, places=6)
                brute = enumerate_partitions(scene, ts, limit=10_000)
                self.assertEqual(brute["partitions"], math.factorial(T) ** 2)
                self.assertAlmostEqual(brute["cost"], best, places=9)


class TestIlpSolution(unittest.TestCase):
    def test_solution_is_a_partition_with_matching_cost(self):
        rng = np.random.default_rng(32)
        params = Params()
        for T in (2, 4, 6):
            for _ in range(15):
                scene = generate(T, params, rng)
                ts = build_tuples(scene, params)
                ilp = solve_ilp(scene, ts)
                self.assertEqual(ilp["status"], "optimal")
                self.assertTrue(is_partition(scene, ilp["partition"]))
                self.assertAlmostEqual(partition_cost(ts, ilp["partition"]), ilp["cost"], places=6)

    def test_never_worse_than_the_truth(self):
        rng = np.random.default_rng(33)
        params = Params()
        for _ in range(60):
            scene = generate(4, params, rng)
            ts = build_tuples(scene, params)
            truth_cost = partition_cost(ts, truth_partition(scene))
            if math.isfinite(truth_cost):
                self.assertLessEqual(solve_ilp(scene, ts)["cost"], truth_cost + 1e-6)

    def test_scene_without_measurements(self):
        params = dataclasses.replace(Params(), p_detect=0.5, clutter_per_sensor=1e-9)
        rng = np.random.default_rng(34)
        for _ in range(200):
            scene = generate(1, params, rng)
            if not any(len(m) for m in scene.measurements):
                ts = build_tuples(scene, params)
                self.assertEqual(solve_ilp(scene, ts)["cost"], 0.0)
                self.assertEqual(enumerate_partitions(scene, ts, limit=10)["cost"], 0.0)
                return
        self.fail("no empty scene generated")

    def test_difference_modes(self):
        rng = np.random.default_rng(35)
        params = dataclasses.replace(Params(), p_detect=1.0, clutter_per_sensor=0.0)
        scene = generate(2, params, rng)
        ts = build_tuples(scene, params)
        truth = truth_partition(scene)
        self.assertEqual(difference_modes(scene, truth, truth, partition_cost(ts, truth)), set())

        # swap sensor 2's measurements between the two targets -> two tuples each mixing both targets
        first, second = truth
        swapped = [(first[0], second[1], first[2]), (second[0], first[1], second[2])]
        self.assertEqual(difference_modes(scene, swapped, truth, 0.0), {MODES[1]})

        # break one target into singletons, and mark the truth as cut
        singles = [(first[0], 0, 0), (0, first[1], 0), (0, 0, first[2]), second]
        self.assertEqual(difference_modes(scene, singles, truth, math.inf), {MODES[2], MODES[3]})

    def test_wilson_interval_contains_the_estimate(self):
        low, high = wilson(411, 500)
        self.assertLess(low, 411 / 500)
        self.assertGreater(high, 411 / 500)


if __name__ == "__main__":
    unittest.main()
