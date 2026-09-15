# Tests for P6.2. Each check uses a route that does not depend on the code being tested:
#   - the greedy thresholds solved by hand from the rewards
#   - the T = 4 loop traced by hand
#   - the value-iteration solution checked against its own Bellman equation at off-grid beliefs, and for symmetry
#   - Hellinger distances by hand
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import pathlib
import sys
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p6_loops import (  # noqa: E402
    GAMMA,
    LISTEN,
    OPEN_LEFT,
    OPEN_RIGHT,
    expected_reward,
    greedy_action,
    hellinger,
    run_loop,
    update,
    value_iteration,
)


class TestPlanner(unittest.TestCase):
    def test_greedy_thresholds_by_hand(self):
        # open-right beats listen when 10(1 - p) - 100 p > -1, i.e. p < 11/110 = 0.1
        self.assertEqual(greedy_action(0.0999), OPEN_RIGHT)
        self.assertEqual(greedy_action(0.1001), LISTEN)
        self.assertEqual(greedy_action(0.9001), OPEN_LEFT)
        self.assertEqual(greedy_action(0.5), LISTEN)

    def test_t4_loop_by_hand(self):
        steps = run_loop([0, 0, 0, 0])
        self.assertAlmostEqual(steps[0]["posterior_p_tiger_right"], 0.15)
        self.assertAlmostEqual(steps[1]["posterior_p_tiger_right"], 0.0225 / (0.0225 + 0.7225))
        self.assertEqual([s["action"] for s in steps], ["listen", "listen", "open-right", "listen"])
        self.assertEqual(steps[2]["posterior_p_tiger_right"], 0.5)

    def test_update_is_bayes(self):
        self.assertAlmostEqual(update(0.3, 1, LISTEN), 0.85 * 0.3 / (0.85 * 0.3 + 0.15 * 0.7))
        self.assertEqual(update(0.3, 1, OPEN_LEFT), 0.5)


class TestValueIteration(unittest.TestCase):
    def test_bellman_equation_off_grid_and_symmetry(self):
        vi = value_iteration(points=4001, tol=1e-10)
        grid, V = vi["grid"], vi["V"]
        v = lambda p: float(np.interp(p, grid, V))  # noqa: E731
        for p in (0.123, 0.37, 0.5, 0.81):
            o1 = 0.85 * p + 0.15 * (1 - p)
            listen = -1 + GAMMA * (o1 * v(0.85 * p / o1) + (1 - o1) * v(0.15 * p / (1 - o1)))
            opens = max(float(expected_reward(p, OPEN_LEFT)), float(expected_reward(p, OPEN_RIGHT))) + GAMMA * v(0.5)
            self.assertAlmostEqual(v(p), max(listen, opens), delta=5e-3)
        self.assertTrue(np.allclose(V, V[::-1], atol=1e-6))


class TestHellinger(unittest.TestCase):
    def test_by_hand(self):
        self.assertAlmostEqual(hellinger([1, 0], [0, 1]), 1.0)
        self.assertAlmostEqual(hellinger([0.5, 0.5], [0.5, 0.5]), 0.0)
        p, q = [0.36, 0.64], [0.64, 0.36]
        self.assertAlmostEqual(hellinger(p, q), np.sqrt(0.5 * 2 * (0.6 - 0.8) ** 2))


if __name__ == "__main__":
    unittest.main()
