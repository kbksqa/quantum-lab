# Tests for P1.0. Each check uses a route that does not depend on the code being tested:
#   - the cost formula is compared with scipy's multivariate normal log-density
#   - the Hungarian optimum on the augmented matrix is compared with direct enumeration of associations
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import dataclasses
import math
import pathlib
import sys
import unittest

import numpy as np
from scipy.stats import multivariate_normal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p1_scenario import (  # noqa: E402
    Params,
    augmented_cost,
    brute_force_min_cost,
    evaluate,
    generate,
    pair_cost,
    pure_cost,
    solve_hungarian,
)


class TestCost(unittest.TestCase):
    def test_cost_matches_gaussian_log_likelihood(self):
        rng = np.random.default_rng(1)
        params = Params()
        for _ in range(50):
            scene = generate(3, params, rng)
            for i in range(len(scene.z_pred)):
                for j in range(len(scene.measurements)):
                    _, cost = pair_cost(scene.measurements[j], scene.z_pred[i], scene.S[i],
                                        params.p_detect, scene.clutter_density)
                    log_pdf = multivariate_normal(mean=scene.z_pred[i], cov=scene.S[i]).logpdf(scene.measurements[j])
                    expected = -(math.log(params.p_detect) + log_pdf - math.log(scene.clutter_density))
                    self.assertAlmostEqual(cost, expected, places=9)


class TestHungarian(unittest.TestCase):
    def test_equals_brute_force_on_random_scenes(self):
        rng = np.random.default_rng(2)
        params = Params()
        checked = 0
        for n_targets in (1, 2, 3, 4):
            for _ in range(60):
                scene = generate(n_targets, params, rng)
                C, info = augmented_cost(scene, params)
                hungarian = solve_hungarian(C, info["tracks"], info["measurements"])["total_cost"]
                self.assertAlmostEqual(hungarian, brute_force_min_cost(scene, params), places=9)
                checked += 1
        self.assertEqual(checked, 240)

    def test_gating_is_respected(self):
        rng = np.random.default_rng(3)
        params = Params()
        for _ in range(200):
            scene = generate(3, params, rng)
            C, info = augmented_cost(scene, params)
            association = solve_hungarian(C, info["tracks"], info["measurements"])["association"]
            for i, j in enumerate(association):
                if j is not None:
                    self.assertLessEqual(info["d2"][i, j], params.gate)

    def test_low_noise_recovers_truth(self):
        rng = np.random.default_rng(4)
        params = dataclasses.replace(Params(), p_detect=1.0, clutter_per_scan=0.0, gate=None,
                                     sigma_meas=0.01, sigma_prev_pos=0.01, sigma_prev_vel=0.01,
                                     sigma_accel=0.001, spacing=1000.0)
        for _ in range(50):
            scene = generate(4, params, rng)
            self.assertTrue(evaluate(scene, params, pure=True)["optimum_is_truth"])


class TestStructure(unittest.TestCase):
    def test_reproducible_with_same_seed(self):
        params = Params()
        a = generate(3, params, np.random.default_rng(99))
        b = generate(3, params, np.random.default_rng(99))
        self.assertTrue(np.array_equal(a.measurements, b.measurements))
        self.assertEqual(a.origin, b.origin)
        Ca, _ = augmented_cost(a, params)
        Cb, _ = augmented_cost(b, params)
        self.assertTrue(np.array_equal(np.isinf(Ca), np.isinf(Cb)))
        self.assertTrue(np.allclose(Ca[np.isfinite(Ca)], Cb[np.isfinite(Cb)]))

    def test_matrix_shapes(self):
        rng = np.random.default_rng(5)
        params = Params()
        scene = generate(3, params, rng)
        C, info = augmented_cost(scene, params)
        self.assertEqual(C.shape, (info["tracks"] + info["measurements"],) * 2)

        pure = dataclasses.replace(params, p_detect=1.0, clutter_per_scan=0.0, gate=None)
        scene = generate(3, pure, rng)
        self.assertEqual(pure_cost(scene).shape, (3, 3))


if __name__ == "__main__":
    unittest.main()
