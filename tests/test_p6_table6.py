# Tests for P6.3. Each check uses a route that does not depend on the code being tested:
#   - the horizon-1 lookahead must pick the greedy action (P6.2), and its value must equal the expected reward
#   - a horizon-2 value computed by hand for the uniform belief
#   - the protocol simulator on a policy that always listens gives -1 per step exactly
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p6_loops import GAMMA, LISTEN, OPEN_LEFT, OPEN_RIGHT, expected_reward, greedy_action  # noqa: E402
from p6_table6 import lookahead_policy, q_value, run_protocol  # noqa: E402


class TestLookahead(unittest.TestCase):
    def test_horizon_one_is_greedy(self):
        h1 = lookahead_policy(1)
        for p in (0.02, 0.0999, 0.1001, 0.3, 0.5, 0.8999, 0.9001, 0.97):
            self.assertEqual(h1(p), greedy_action(p))
            for a in (LISTEN, OPEN_LEFT, OPEN_RIGHT):
                self.assertAlmostEqual(q_value(p, a, 1), float(expected_reward(p, a)))

    def test_horizon_two_by_hand_at_uniform_belief(self):
        # listen at 0.5: hear each side with probability 0.5, posterior 0.15 or 0.85, where the best one-step action is
        # listen (-1): Q = -1 + gamma * (-1)
        self.assertAlmostEqual(q_value(0.5, LISTEN, 2), -1 - GAMMA)
        # open at 0.5: expected -45, then belief 0.5 again with best one-step value -1
        self.assertAlmostEqual(q_value(0.5, OPEN_LEFT, 2), -45 + GAMMA * -1)


class TestProtocol(unittest.TestCase):
    def test_always_listen(self):
        r = run_protocol(lambda p: LISTEN, "continue", False, episodes=5, steps=50)
        self.assertAlmostEqual(r["mean"], -50.0)
        self.assertAlmostEqual(r["sd"], 0.0)
        r = run_protocol(lambda p: LISTEN, "continue", True, episodes=3, steps=10)
        self.assertAlmostEqual(r["mean"], -sum(GAMMA ** t for t in range(10)))


if __name__ == "__main__":
    unittest.main()
