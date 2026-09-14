# Tests for P2.0. Each check uses a route that does not depend on the code being tested:
#   - the measurement covariance is compared with the Jacobian of the polar-to-Cartesian map (finite differences)
#   - the fused estimate and the tuple cost are compared with a numerical minimisation of scipy's Gaussian log-density
#   - the tuple enumeration is compared with the product of the measurement counts
#   - on low-noise pure scenes the truth is compared with every partition, enumerated directly
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
from scipy.optimize import minimize
from scipy.stats import multivariate_normal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p2_scene import (  # noqa: E402
    PURE,
    Params,
    build_tuples,
    fuse,
    generate,
    is_partition,
    measurement_covariance,
    partition_cost,
    target_cost,
    truth_partition,
)


def tuple_measurements(scene, tup):
    detected = [s for s in range(len(tup)) if tup[s] > 0]
    zs = [scene.measurements[s][tup[s] - 1] for s in detected]
    Rs = [scene.covariances[s][tup[s] - 1] for s in detected]
    return zs, Rs, len(tup) - len(detected)


class TestCovariance(unittest.TestCase):
    def test_matches_polar_jacobian(self):
        rng = np.random.default_rng(10)
        sigma_range, sigma_bearing = 10.0, 0.02
        for _ in range(50):
            sensor = rng.uniform(-3000, 3000, 2)
            position = rng.uniform(-300, 300, 2)
            offset = position - sensor
            r, theta = math.hypot(*offset), math.atan2(offset[1], offset[0])

            def to_xy(rt):
                return sensor + rt[0] * np.array([math.cos(rt[1]), math.sin(rt[1])])

            h = 1e-6
            J = np.column_stack([(to_xy([r + h, theta]) - to_xy([r - h, theta])) / (2 * h),
                                 (to_xy([r, theta + h]) - to_xy([r, theta - h])) / (2 * h)])
            expected = J @ np.diag([sigma_range ** 2, sigma_bearing ** 2]) @ J.T
            self.assertTrue(np.allclose(measurement_covariance(position, sensor, sigma_range, sigma_bearing),
                                        expected, rtol=1e-6, atol=1e-6))


class TestTupleCost(unittest.TestCase):
    def check_against_numerical(self, scene, params, tup):
        zs, Rs, n_missing = tuple_measurements(scene, tup)

        def negative_log_likelihood(x):
            return -sum(multivariate_normal(mean=x, cov=R).logpdf(z) for z, R in zip(zs, Rs))

        found = minimize(negative_log_likelihood, np.mean(zs, axis=0), method="BFGS")
        x_hat, _ = fuse(zs, Rs)
        self.assertLess(np.linalg.norm(found.x - x_hat), 1e-2)

        log_lambda = math.log(scene.clutter_density) if scene.clutter_density > 0 else 0.0
        expected = found.fun + len(zs) * (log_lambda - math.log(params.p_detect))
        if n_missing:
            expected -= n_missing * math.log(1 - params.p_detect)
        cost = target_cost(zs, Rs, n_missing, params.p_detect, scene.clutter_density)
        self.assertAlmostEqual(cost, expected, places=6)

    def test_matches_numerical_likelihood(self):
        rng = np.random.default_rng(11)
        params = dataclasses.replace(Params(), gate=None)
        checked = 0
        for _ in range(30):
            scene = generate(3, params, rng)
            sizes = [len(m) for m in scene.measurements]
            for tup in itertools.product(*[range(m + 1) for m in sizes]):
                if any(tup) and rng.random() < 0.15:
                    self.check_against_numerical(scene, params, tup)
                    checked += 1
        self.assertGreater(checked, 300)

    def test_pure_mode_matches_numerical_likelihood(self):
        rng = np.random.default_rng(12)
        params = dataclasses.replace(Params(), **PURE)
        for _ in range(20):
            scene = generate(2, params, rng)
            for tup in build_tuples(scene, params).tuples:
                self.check_against_numerical(scene, params, tup)


class TestTupleSet(unittest.TestCase):
    def test_every_enumerated_tuple_is_accounted_for(self):
        rng = np.random.default_rng(13)
        params = Params()
        for T in (1, 2, 3, 4, 5):
            for _ in range(20):
                scene = generate(T, params, rng)
                ts = build_tuples(scene, params)
                c = ts.counts
                self.assertEqual(c["enumerated"], math.prod(len(m) + 1 for m in scene.measurements) - 1)
                self.assertEqual(c["enumerated"], len(ts.tuples) + c["removed_by_gate"] + c["removed_infinite_cost"])
                singletons = sum(sum(1 for i in tup if i > 0) == 1 for tup in ts.tuples)
                self.assertEqual(singletons, c["singleton_as_target"] + c["singleton_as_false_alarm"])

    def test_kept_tuples_pass_every_pairwise_gate(self):
        rng = np.random.default_rng(14)
        params = Params()
        for _ in range(40):
            scene = generate(4, params, rng)
            for tup in build_tuples(scene, params).tuples:
                zs, Rs, _ = tuple_measurements(scene, tup)
                for a, b in itertools.combinations(range(len(zs)), 2):
                    d = zs[a] - zs[b]
                    self.assertLessEqual(float(d @ np.linalg.inv(Rs[a] + Rs[b]) @ d), params.gate)

    def test_gate_rejects_about_one_percent_of_true_pairs(self):
        # A true pair's difference is N(0, R_a + R_b), so a 99% chi-square gate should reject about 1% of them.
        rng = np.random.default_rng(20)
        params = Params()
        rejected = total = 0
        for _ in range(2000):
            scene = generate(4, params, rng)
            for a, b in itertools.combinations(range(3), 2):
                for i, source_i in enumerate(scene.origin[a]):
                    for j, source_j in enumerate(scene.origin[b]):
                        if source_i >= 0 and source_i == source_j:
                            total += 1
                            d = scene.measurements[a][i] - scene.measurements[b][j]
                            R = scene.covariances[a][i] + scene.covariances[b][j]
                            rejected += float(d @ np.linalg.inv(R) @ d) > params.gate
        self.assertGreater(total, 15000)
        self.assertTrue(0.007 < rejected / total < 0.013)

    def test_all_singletons_is_always_feasible_with_clutter(self):
        rng = np.random.default_rng(15)
        params = Params()
        for _ in range(40):
            scene = generate(4, params, rng)
            ts = build_tuples(scene, params)
            singles = [tuple(j + 1 if s == k else 0 for k in range(len(scene.sensors)))
                       for s in range(len(scene.sensors)) for j in range(len(scene.measurements[s]))]
            self.assertTrue(is_partition(scene, singles))
            self.assertTrue(math.isfinite(partition_cost(ts, singles)))

    def test_false_alarm_singletons_cost_zero(self):
        rng = np.random.default_rng(16)
        params = Params()
        scene = generate(3, params, rng)
        ts = build_tuples(scene, params)
        for cost, fa in zip(ts.costs, ts.false_alarm):
            if fa:
                self.assertEqual(cost, 0.0)

    def test_pure_mode_keeps_only_full_tuples(self):
        rng = np.random.default_rng(17)
        params = dataclasses.replace(Params(), **PURE)
        for T in (1, 2, 3):
            scene = generate(T, params, rng)
            ts = build_tuples(scene, params)
            self.assertEqual(len(ts.tuples), T ** 3)
            self.assertTrue(all(all(i > 0 for i in tup) for tup in ts.tuples))
            self.assertFalse(any(ts.false_alarm))


class TestTruth(unittest.TestCase):
    def test_truth_is_a_partition(self):
        rng = np.random.default_rng(18)
        params = Params()
        for T in (1, 2, 3, 4, 5, 6):
            for _ in range(20):
                scene = generate(T, params, rng)
                self.assertTrue(is_partition(scene, truth_partition(scene)))

    def test_low_noise_truth_is_the_cheapest_partition(self):
        rng = np.random.default_rng(19)
        params = dataclasses.replace(Params(), **PURE, sigma_range=0.1, sigma_bearing=1e-4, spacing=500.0)
        for _ in range(20):
            scene = generate(3, params, rng)
            ts = build_tuples(scene, params)
            best = min(partition_cost(ts, [(i + 1, p2[i] + 1, p3[i] + 1) for i in range(3)])
                       for p2 in itertools.permutations(range(3)) for p3 in itertools.permutations(range(3)))
            self.assertAlmostEqual(partition_cost(ts, truth_partition(scene)), best, places=9)

    def test_reproducible_with_same_seed(self):
        params = Params()
        a = generate(4, params, np.random.default_rng(99))
        b = generate(4, params, np.random.default_rng(99))
        for s in range(3):
            self.assertTrue(np.array_equal(a.measurements[s], b.measurements[s]))
            self.assertEqual(a.origin[s], b.origin[s])
        ta, tb = build_tuples(a, params), build_tuples(b, params)
        self.assertEqual(ta.tuples, tb.tuples)
        self.assertTrue(np.array_equal(ta.costs, tb.costs))


if __name__ == "__main__":
    unittest.main()
