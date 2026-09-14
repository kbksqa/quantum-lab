# Tests for P2.4. The checker is tested against answers whose correctness is known by construction:
#   - the ILP partition must score valid, optimal, zero gap; the truth must score equals_truth
#   - broken answers (reused, missing, unknown or malformed tuples) must be rejected
#   - an instance written to disk and read back must regenerate identically from its own seed
#   - normalised greedy must shift every partition by the same constant (checked on two different partitions)
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import dataclasses
import gzip
import json
import math
import pathlib
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p2_benchmark import SWEEP, check, load_instances, make_instance, settings  # noqa: E402
from p2_heuristics import measurement_reference  # noqa: E402
from p2_ilp import solve_ilp  # noqa: E402
from p2_qubo import members  # noqa: E402
from p2_scene import Params, build_tuples, generate, partition_cost, truth_partition  # noqa: E402


def some_instances(n):
    chosen = [i for i, s in enumerate(settings()) if s["targets"] == 3][:n]
    return [make_instance(i, settings()[i], 0) for i in chosen]


class TestSweep(unittest.TestCase):
    def test_setting_count(self):
        self.assertEqual(len(settings()), math.prod(len(v) for v in SWEEP.values()))
        self.assertEqual(len(settings()), 540)
        self.assertIn(0.005, SWEEP["sigma_bearing"])


class TestChecker(unittest.TestCase):
    def test_optimum_and_truth_score_as_expected(self):
        for instance, scene, ts, _ in some_instances(12):
            if instance["optimum"] is None:
                continue
            s = check(instance, instance["optimum"]["partition"])
            self.assertTrue(s["valid"], s)
            self.assertTrue(s["optimal"])
            self.assertAlmostEqual(s["gap_to_optimum"], 0.0, places=9)
            self.assertAlmostEqual(s["cost"], partition_cost(ts, [tuple(t) for t in instance["optimum"]["partition"]]))
            truth = check(instance, instance["truth"]["partition"])
            self.assertEqual(truth["valid"], all(tuple(t) in ts.tuples for t in instance["truth"]["partition"]))
            if truth["valid"]:
                self.assertTrue(truth["equals_truth"])
                self.assertEqual(truth["truth_tuples_recovered"], 1.0)

    def test_broken_answers_are_rejected(self):
        instance, _, _, _ = next(x for x in some_instances(12) if x[0]["optimum"] and len(x[0]["optimum"]["partition"]) >= 2)
        good = instance["optimum"]["partition"]
        self.assertFalse(check(instance, good[1:])["valid"])                        # a measurement left out
        self.assertFalse(check(instance, good + [good[0]])["valid"])                # a tuple used twice
        self.assertFalse(check(instance, [[0, 0, 0]] + good)["valid"])              # empty tuple
        self.assertFalse(check(instance, [[99, 0, 0]] + good)["valid"])             # index out of range
        self.assertFalse(check(instance, None)["valid"])                           # no answer at all
        forbidden = [t for t in ([a, b, c] for a in range(len(instance["measurements"][0]) + 1)
                                 for b in range(len(instance["measurements"][1]) + 1)
                                 for c in range(len(instance["measurements"][2]) + 1))
                     if any(t) and t not in instance["tuples"]]
        if forbidden:
            s = check(instance, [forbidden[0]] + good)
            self.assertFalse(s["valid"])
            self.assertTrue(any("not an allowed tuple" in p for p in s["problems"]))


class TestFiles(unittest.TestCase):
    def test_round_trip_and_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "i.jsonl.gz"
            built = some_instances(4)
            with gzip.open(path, "wt", encoding="utf-8") as f:
                for instance, _, _, _ in built:
                    f.write(json.dumps(instance) + "\n")
            loaded = load_instances(path)
        self.assertEqual([b[0] for b in built], loaded)
        for instance in loaded:
            p = instance["generator"]["params"]
            params = dataclasses.replace(Params(), **p)
            scene = generate(instance["generator"]["targets"], params, np.random.default_rng(instance["generator"]["seed"]))
            ts = build_tuples(scene, params)
            self.assertEqual([list(t) for t in ts.tuples], instance["tuples"])
            self.assertEqual(ts.costs.tolist(), instance["costs"])
            self.assertEqual([list(t) for t in truth_partition(scene)], instance["truth"]["partition"])


class TestNormalisation(unittest.TestCase):
    def test_shift_is_the_same_for_every_partition(self):
        rng = np.random.default_rng(60)
        for change in ({}, {"clutter_per_sensor": 0.0}, {"p_detect": 1.0}):
            params = dataclasses.replace(Params(), **change)
            for _ in range(10):
                scene = generate(3, params, rng)
                ts = build_tuples(scene, params)
                ilp = solve_ilp(scene, ts)
                if ilp["status"] != "optimal":
                    continue
                ref = measurement_reference(scene, params.p_detect)
                shift = sum(ref.values())
                shifted = {t: c - sum(ref[m] for m in members(t)) for t, c in zip(ts.tuples, ts.costs)}
                candidates = [ilp["partition"]]
                singles = [tuple(j if k == s else 0 for k in range(3)) for s in range(3)
                           for j in range(1, len(scene.measurements[s]) + 1)]
                if all(t in shifted for t in singles):
                    candidates.append(singles)
                for partition in candidates:
                    self.assertAlmostEqual(sum(shifted[t] for t in partition), partition_cost(ts, partition) - shift,
                                           places=8)


if __name__ == "__main__":
    unittest.main()
