# Tests for P2.2. The QUBO is checked against quantities computed without the QUBO:
#   - on a valid partition the energy must equal the partition cost from the tuple table
#   - on any bit string, energy - cost must equal A times the squared cover violation, counted directly
#   - the brute-force QUBO minimum must equal the ILP optimum, and its argmin must decode to an optimal partition
#   - with two sensors the matrix must match the P1 form (diagonal c - 2A for pairs)
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import dataclasses
import pathlib
import sys
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p1_qubo import brute_force_minimum, energy  # noqa: E402
from p2_ilp import solve_ilp  # noqa: E402
from p2_qubo import build_qubo, check_instance, decode, safe_penalty  # noqa: E402
from p2_scene import PURE, Params, build_tuples, generate, partition_cost, truth_partition  # noqa: E402


def small_scene(rng, T, change, max_vars):
    params = dataclasses.replace(Params(), **change)
    for _ in range(200):
        scene = generate(T, params, rng)
        ts = build_tuples(scene, params)
        if 0 < len(ts.tuples) <= max_vars and solve_ilp(scene, ts)["status"] == "optimal":
            return scene, ts
    raise AssertionError("no small scene found")


class TestAlgebra(unittest.TestCase):
    def test_feasible_energy_equals_partition_cost(self):
        rng = np.random.default_rng(40)
        params = Params()
        for T in (1, 2, 3, 4):
            for _ in range(15):
                scene = generate(T, params, rng)
                ts = build_tuples(scene, params)
                qubo = build_qubo(scene, ts)
                partitions = [solve_ilp(scene, ts)["partition"]]
                truth = truth_partition(scene)
                if all(tup in ts.tuples for tup in truth):
                    partitions.append(truth)
                for partition in partitions:
                    x = np.array([tup in partition for tup in ts.tuples], dtype=int)
                    self.assertAlmostEqual(float(energy(qubo, x)[0]), partition_cost(ts, partition),
                                           delta=1e-7 * qubo["penalty"])

    def test_penalty_equals_squared_cover_violation(self):
        rng = np.random.default_rng(41)
        params = Params()
        for _ in range(150):
            scene = generate(int(rng.integers(1, 4)), params, rng)
            ts = build_tuples(scene, params)
            if not ts.tuples:
                continue
            qubo = build_qubo(scene, ts, penalty=float(rng.uniform(0.5, 50)))
            x = rng.integers(0, 2, size=len(ts.tuples))
            cost = float(sum(c for bit, c in zip(x, ts.costs) if bit))
            cover = {(s, j + 1): 0 for s in range(3) for j in range(len(scene.measurements[s]))}
            for bit, tup in zip(x, ts.tuples):
                for s, i in enumerate(tup):
                    if bit and i > 0:
                        cover[s, i] += 1
            violation = float(sum((n - 1) ** 2 for n in cover.values()))
            self.assertAlmostEqual(float(energy(qubo, x)[0]) - cost, qubo["penalty"] * violation, delta=1e-6)

    def test_two_sensors_match_the_p1_diagonal(self):
        rng = np.random.default_rng(42)
        params = dataclasses.replace(Params(), n_sensors=2)
        scene = generate(3, params, rng)
        ts = build_tuples(scene, params)
        qubo = build_qubo(scene, ts)
        A = qubo["penalty"]
        for k, tup in enumerate(ts.tuples):
            expected = ts.costs[k] - (2 * A if all(i > 0 for i in tup) else A)
            self.assertAlmostEqual(qubo["Q"][k, k], expected, places=9)
        self.assertTrue(np.all(np.isin(np.triu(qubo["Q"], 1), [0.0, 2 * A])))

    def test_default_penalty_rule(self):
        self.assertAlmostEqual(safe_penalty(np.array([1.0, -2.0, 3.0, 0.0])), 13.0)


class TestGate(unittest.TestCase):
    def test_qubo_minimum_equals_ilp(self):
        rng = np.random.default_rng(43)
        tested = 0
        for T, change in ((1, {}), (2, dict(PURE)), (2, {"sigma_bearing": 0.005}),
                          (3, {"p_detect": 1.0, "clutter_per_sensor": 0.0, "sigma_bearing": 0.005})):
            for _ in range(8):
                scene, ts = small_scene(rng, T, change, max_vars=14)
                record = check_instance(scene, ts, max_vars=14)
                self.assertEqual(record["status"], "pass", record)
                tested += 1
        self.assertEqual(tested, 32)

    def test_argmin_decodes_to_an_optimal_partition(self):
        rng = np.random.default_rng(44)
        for _ in range(10):
            scene, ts = small_scene(rng, 2, dict(PURE), max_vars=14)
            qubo = build_qubo(scene, ts)
            _, x = brute_force_minimum(qubo, 14)
            feasible, partition = decode(x, qubo, scene)
            self.assertTrue(feasible)
            self.assertAlmostEqual(partition_cost(ts, partition), solve_ilp(scene, ts)["cost"], places=6)


if __name__ == "__main__":
    unittest.main()
