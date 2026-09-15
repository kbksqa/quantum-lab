# Tests for P2.8. Each check uses a route that does not depend on the code being tested:
#   - the marginal cost is compared with numerical integration of the likelihood over the scene window
#   - the ILP under marginal costs is compared with exact-cover enumeration
#   - dissolved recovery is re-checked as a partition, re-costed from the tuple table, and compared with the original
#   - CVaR is compared with an expanded list of equally likely outcomes, and with <H> at alpha = 1
#   - the H5-day script refuses to submit without a plan, and its grading thresholds are checked at the boundaries
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import dataclasses
import math
import pathlib
import subprocess
import sys
import unittest

import numpy as np
from scipy.integrate import quad

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p2_8_followup import cvar, joined_clutter, marginal_tuple_set, window_area  # noqa: E402
from p2_8_h5_day import grade  # noqa: E402
from p2_heuristics import lagrangian_relaxation, lagrangian_value, lr_structure, recover  # noqa: E402
from p2_ilp import enumerate_partitions, solve_ilp  # noqa: E402
from p2_scene import Params, build_tuples, fuse, generate, is_partition, partition_cost, truth_partition  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def gaussian(z, R, x):
    d = z - x
    return math.exp(-0.5 * float(d @ np.linalg.solve(R, d))) / math.sqrt(np.linalg.det(2 * math.pi * R))


class TestMarginalCost(unittest.TestCase):
    def test_closed_form_matches_numerical_integration(self):
        rng = np.random.default_rng(80)
        params = Params()
        checked = 0
        while checked < 6:
            scene = generate(2, params, rng)
            ts = build_tuples(scene, params)
            marginal = marginal_tuple_set(scene, ts, params)
            area = window_area(scene, params)
            low = scene.targets.min(axis=0) - params.window_pad
            high = scene.targets.max(axis=0) + params.window_pad
            for tup, cost, fa in zip(marginal.tuples, marginal.costs, marginal.false_alarm):
                detected = [s for s in range(3) if tup[s] > 0]
                if len(detected) < 2 or fa:
                    continue
                zs = [scene.measurements[s][tup[s] - 1] for s in detected]
                Rs = [scene.covariances[s][tup[s] - 1] for s in detected]
                centre, _ = fuse(zs, Rs)

                def inner(y):
                    return quad(lambda x: math.prod(gaussian(z, R, np.array([x, y])) for z, R in zip(zs, Rs)),
                                low[0], high[0], points=[centre[0]], limit=200, epsabs=0, epsrel=1e-11)[0]

                integral = quad(inner, low[1], high[1], points=[centre[1]], limit=200, epsabs=0, epsrel=1e-11)[0]
                n_missing = 3 - len(detected)
                expected = (sum(-math.log(params.p_detect) + math.log(scene.clutter_density) for _ in detected)
                            - n_missing * math.log(1 - params.p_detect) + math.log(area) - math.log(integral))
                self.assertAlmostEqual(cost, expected, delta=1e-6)
                checked += 1
                break

    def test_same_tuples_and_singleton_rule(self):
        rng = np.random.default_rng(81)
        for change in ({}, {"clutter_per_sensor": 0.0}, {"p_detect": 1.0}):
            params = dataclasses.replace(Params(), **change)
            for _ in range(10):
                scene = generate(3, params, rng)
                ts = build_tuples(scene, params)
                marginal = marginal_tuple_set(scene, ts, params)
                self.assertEqual(marginal.tuples, ts.tuples)
                for tup, cost, fa in zip(marginal.tuples, marginal.costs, marginal.false_alarm):
                    if sum(i > 0 for i in tup) == 1 and scene.clutter_density > 0:
                        self.assertLessEqual(cost, 0.0 + 1e-12)
                        self.assertEqual(fa, cost == 0.0)
                    else:
                        self.assertFalse(fa)
                        self.assertTrue(math.isfinite(cost))

    def test_ilp_matches_enumeration_under_marginal_costs(self):
        rng = np.random.default_rng(82)
        checked = 0
        for change in ({}, {"clutter_per_sensor": 0.0}, {"p_detect": 1.0}):
            params = dataclasses.replace(Params(), **change)
            for T in (1, 2, 3):
                for _ in range(4):
                    scene = generate(T, params, rng)
                    ts = marginal_tuple_set(scene, build_tuples(scene, params), params)
                    ilp = solve_ilp(scene, ts)
                    brute = enumerate_partitions(scene, ts, 200_000)
                    if brute is None or ilp["status"] not in ("optimal", "empty"):
                        continue
                    self.assertAlmostEqual(ilp["cost"], brute["cost"], delta=1e-6 * max(1.0, abs(brute["cost"])))
                    checked += 1
        self.assertGreater(checked, 20)

    def test_joined_clutter_counts_by_hand(self):
        rng = np.random.default_rng(83)
        params = dataclasses.replace(Params(), clutter_per_sensor=2.0)
        scene = next(s for s in (generate(2, params, rng) for _ in range(50))
                     if any(o < 0 for per in s.origin for o in per))
        s, j = next((s, j) for s in range(3) for j, o in enumerate(scene.origin[s]) if o < 0)
        truth = truth_partition(scene)
        self.assertEqual(joined_clutter(scene, truth), 0)
        single = tuple(j + 1 if k == s else 0 for k in range(3))
        # take one real measurement from another sensor out of its target tuple and pair it with the clutter measurement
        target, k = next((t, k) for t in truth for k in range(3)
                         if k != s and t[k] > 0 and scene.origin[k][t[k] - 1] >= 0)
        rest = tuple(0 if q == k else target[q] for q in range(3))
        pair = tuple(j + 1 if q == s else (target[k] if q == k else 0) for q in range(3))
        changed = sorted([t for t in truth if t not in (single, target)] + [pair] + ([rest] if any(rest) else []))
        self.assertTrue(is_partition(scene, changed))
        self.assertEqual(joined_clutter(scene, changed), 1)


class TestDissolvedRecovery(unittest.TestCase):
    def test_valid_whenever_a_partition_exists_at_full_detection(self):
        rng = np.random.default_rng(84)
        params = dataclasses.replace(Params(), p_detect=1.0, clutter_per_sensor=2.0, spacing=25.0)
        checked = 0
        for T in (3, 4, 5):
            for _ in range(15):
                scene = generate(T, params, rng)
                ts = build_tuples(scene, params)
                ilp = solve_ilp(scene, ts)
                if ilp["status"] != "optimal":
                    continue
                lr = lagrangian_relaxation(scene, ts, dissolve=True)
                self.assertTrue(is_partition(scene, lr["partition"]))
                self.assertAlmostEqual(partition_cost(ts, lr["partition"]), lr["upper_bound"], places=9)
                self.assertGreaterEqual(lr["upper_bound"], ilp["cost"] - 1e-6 * max(1.0, abs(ilp["cost"])))
                checked += 1
        self.assertGreater(checked, 30)

    def test_never_worse_than_keeping_every_pair(self):
        rng = np.random.default_rng(85)
        for change in ({}, {"p_detect": 1.0}):
            params = dataclasses.replace(Params(), **change)
            for _ in range(20):
                scene = generate(4, params, rng)
                ts = build_tuples(scene, params)
                structure = lr_structure(ts)
                u = np.concatenate([[0.0], rng.normal(0, 3, len(scene.measurements[2]))])
                _, chosen = lagrangian_value(scene, ts, u, structure)
                kept, _ = recover(scene, ts, chosen, structure[0])
                dissolved, partition = recover(scene, ts, chosen, structure[0], dissolve=True)
                self.assertLessEqual(dissolved, kept + 1e-9)
                if partition is not None:
                    self.assertTrue(is_partition(scene, partition))
                    self.assertAlmostEqual(partition_cost(ts, partition), dissolved, places=9)


class TestCvar(unittest.TestCase):
    def test_alpha_one_is_the_expectation(self):
        rng = np.random.default_rng(86)
        probs = rng.random(16)
        probs /= probs.sum()
        energies = rng.normal(size=16)
        self.assertAlmostEqual(cvar(probs, energies, 1.0), float(probs @ energies), places=12)

    def test_matches_expanded_outcomes(self):
        rng = np.random.default_rng(87)
        for _ in range(20):
            counts = rng.integers(0, 6, 8)
            counts[0] += 1
            n = int(counts.sum())
            energies = rng.integers(-5, 5, 8).astype(float)
            outcomes = np.sort(np.repeat(energies, counts))
            for k in range(1, n + 1):
                self.assertAlmostEqual(cvar(counts / n, energies, k / n), float(outcomes[:k].mean()), places=12)


class TestH5Day(unittest.TestCase):
    def test_grading_thresholds(self):
        self.assertEqual(grade(0.890), "held")
        self.assertEqual(grade(0.940), "held")
        self.assertEqual(grade(0.839), "partly held")
        self.assertEqual(grade(0.990), "partly held")
        self.assertEqual(grade(0.789), "failed")

    def test_submit_without_plan_is_refused(self):
        run = subprocess.run([sys.executable, str(ROOT / "src" / "p2_8_h5_day.py")], capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("registered plan", run.stderr)


if __name__ == "__main__":
    unittest.main()
