# Tests for P3.1. Each check uses a route that does not depend on the code being tested:
#   - costs are compared with scipy's Gaussian log-density (plus the clutter term for the "code" variant)
#   - on any bit string, E(x) = cost(x) + lambda * V(x) - lambda (N + M), with cost and V counted directly
#   - the Hungarian-as-coded value is compared with a direct enumeration of maximum-cardinality associations
#   - brute force over all strings is compared with enumeration of valid associations
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import itertools
import math
import pathlib
import sys
import unittest

import numpy as np
from scipy.stats import multivariate_normal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p3_qantis_instance import (  # noqa: E402
    CLUTTER_DENSITY,
    all_strings,
    association_vector,
    associations,
    brute_force,
    build_qubo,
    cost_matrix,
    energy,
    generate,
    gnn_as_coded,
    hungarian_as_coded,
    index_map,
)


def random_instance(rng, N, M):
    scene = {"predicted": rng.standard_normal((N, 2)), "measurements": rng.standard_normal((M, 2)),
             "S": np.stack([0.5 * np.eye(2)] * N)}
    C, mask, _ = cost_matrix(scene, "code")
    return scene, C, mask, build_qubo(C, mask)


class TestCosts(unittest.TestCase):
    def test_costs_match_gaussian_log_density(self):
        scene = generate()
        for variant, shift in (("code", math.log(CLUTTER_DENSITY)), ("paper", 0.0)):
            C, mask, _ = cost_matrix(scene, variant)
            for i in range(2):
                for j in range(3):
                    if mask[i, j]:
                        logpdf = multivariate_normal(mean=scene["predicted"][i], cov=scene["S"][i]).logpdf(scene["measurements"][j])
                        self.assertAlmostEqual(C[i, j], -logpdf + shift, places=9)
                    else:
                        self.assertEqual(C[i, j], 0.0)

    def test_generator_draw_order(self):
        rng = np.random.default_rng(42)
        scene = generate()
        self.assertTrue(np.array_equal(scene["predicted"], rng.standard_normal((2, 2))))
        self.assertTrue(np.array_equal(scene["measurements"], rng.standard_normal((3, 2))))


class TestQubo(unittest.TestCase):
    def test_energy_decomposition_on_random_strings(self):
        rng = np.random.default_rng(80)
        for _ in range(10):
            N, M = int(rng.integers(1, 4)), int(rng.integers(1, 4))
            _, C, mask, qubo = random_instance(rng, N, M)
            idx = index_map(N, M)
            X = rng.integers(0, 2, size=(200, len(idx)))
            for x in X:
                cost = sum(C[i, j] * x[idx["x", i, j]] for i in range(N) for j in range(M) if mask[i, j])
                cost += 5.0 * sum(x[idx["m", i]] for i in range(N)) + 3.0 * sum(x[idx["f", j]] for j in range(M))
                V = sum((sum(x[idx["x", i, j]] for j in range(M)) + x[idx["m", i]] - 1) ** 2 for i in range(N))
                V += sum((sum(x[idx["x", i, j]] for i in range(N)) + x[idx["f", j]] - 1) ** 2 for j in range(M))
                self.assertAlmostEqual(float(energy(qubo, x)[0]), cost + qubo["penalty"] * (V - N - M), places=8)

    def test_variable_and_term_counts(self):
        scene = generate()
        C, mask, _ = cost_matrix(scene)
        qubo = build_qubo(C, mask)
        self.assertEqual(qubo["Q"].shape, (11, 11))
        self.assertEqual(int(np.count_nonzero(np.triu(qubo["Q"], 1))), 2 * math.comb(4, 2) + 3 * math.comb(3, 2))


class TestReferences(unittest.TestCase):
    def test_hungarian_as_coded_is_best_maximum_cardinality_association(self):
        rng = np.random.default_rng(81)
        for _ in range(30):
            N, M = int(rng.integers(1, 4)), int(rng.integers(1, 4))
            _, _, _, qubo = random_instance(rng, N, M)
            k = min(N, M)
            best = min(float(energy(qubo, association_vector(a, N, M))[0])
                       for a in associations(N, M) if sum(c is not None for c in a) == k)
            self.assertAlmostEqual(hungarian_as_coded(qubo)["objective"], best, places=8)

    def test_brute_force_matches_enumeration_of_associations(self):
        rng = np.random.default_rng(82)
        for _ in range(10):
            N, M = int(rng.integers(1, 3)), int(rng.integers(1, 4))
            _, _, _, qubo = random_instance(rng, N, M)
            bf = brute_force(qubo)
            enumerated = min(float(energy(qubo, association_vector(a, N, M))[0]) for a in associations(N, M))
            self.assertAlmostEqual(bf["min_feasible_energy"], enumerated, places=8)
            self.assertEqual(bf["feasible_count"], sum(1 for _ in associations(N, M)))

    def test_gnn_full_objective_is_its_energy(self):
        rng = np.random.default_rng(83)
        _, _, _, qubo = random_instance(rng, 2, 3)
        g = gnn_as_coded(qubo)
        self.assertAlmostEqual(g["objective_full"], float(energy(qubo, g["vector"])[0]), places=9)

    def test_strings_enumeration(self):
        X = all_strings(3)
        self.assertEqual(len({tuple(x) for x in X}), 8)
        self.assertTrue(all(list(x) == [(k >> b) & 1 for b in range(3)] for k, x in enumerate(X)))


if __name__ == "__main__":
    unittest.main()
