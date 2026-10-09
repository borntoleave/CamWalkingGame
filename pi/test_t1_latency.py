"""Tests for the T1 gate decision.

Run from the repo root on a laptop, no Pi and no robot needed:

    python3 -m unittest discover -s pi -p 'test_*.py' -v

Everything else in t1_latency.py is I/O (camera, MediaPipe, serial, clock).
`evaluate` is the only judgement in the file, and it decides whether a project
continues. These tests exist because a flipped comparison or an off-by-one in
the percentile index would pass a run that should have stopped.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import t1_latency as t1


def samples(n, value):
    return [float(value)] * n


class TestGate(unittest.TestCase):

    def test_clearly_good_run_passes(self):
        r = t1.evaluate(samples(150, 120.0), samples(150, 90.0), 150, 30.0)
        self.assertTrue(r["passed"])
        self.assertTrue(r["pass_p95"])
        self.assertTrue(r["pass_fps"])
        self.assertAlmostEqual(r["fps"], 5.0)

    def test_slow_latency_fails_even_at_good_fps(self):
        # 5 fps is comfortable, but every observation is half a second old.
        # This is exactly the case average-fps reporting would have hidden.
        r = t1.evaluate(samples(150, 500.0), samples(150, 150.0), 150, 30.0)
        self.assertFalse(r["passed"])
        self.assertFalse(r["pass_p95"])
        self.assertTrue(r["pass_fps"])

    def test_low_fps_fails_even_with_fresh_frames(self):
        r = t1.evaluate(samples(60, 100.0), samples(60, 80.0), 60, 30.0)
        self.assertFalse(r["passed"])
        self.assertTrue(r["pass_p95"])
        self.assertFalse(r["pass_fps"])

    def test_p95_ignores_a_good_median_with_a_bad_tail(self):
        # 90% fast, 10% very slow. The median looks fine and the mean is
        # survivable; p95 is what catches it.
        lat = samples(90, 100.0) + samples(10, 900.0)
        r = t1.evaluate(lat, samples(100, 80.0), 100, 20.0)
        self.assertEqual(r["p50"], 100.0)
        self.assertFalse(r["pass_p95"])
        self.assertFalse(r["passed"])

    def test_gate_boundaries_are_inclusive_as_specified(self):
        exactly = t1.evaluate(samples(100, t1.GATE_P95_MS), samples(100, 50.0),
                              100, 100.0 / t1.GATE_MIN_FPS)
        self.assertTrue(exactly["pass_p95"], "p95 == 400ms should pass, the spec says <=")
        self.assertTrue(exactly["pass_fps"], "fps == 3.0 should pass, the spec says >=")

    def test_just_past_each_boundary_fails(self):
        slow = t1.evaluate(samples(100, t1.GATE_P95_MS + 1), samples(100, 50.0), 100, 20.0)
        self.assertFalse(slow["pass_p95"])
        few = t1.evaluate(samples(59, 100.0), samples(59, 50.0), 59, 20.0)
        self.assertFalse(few["pass_fps"])

    def test_percentile_index_never_overruns(self):
        # int(n * 0.95) reaches n for small n, which would IndexError without
        # the min() guard. Walk every length the gate will accept.
        for n in range(10, 60):
            r = t1.evaluate(samples(n, 100.0), samples(n, 50.0), n, 10.0)
            self.assertEqual(r["p95"], 100.0, f"n={n}")

    def test_unsorted_input_is_handled(self):
        lat = [900.0, 100.0, 100.0] + samples(97, 100.0)
        r = t1.evaluate(lat, samples(100, 50.0), 100, 20.0)
        self.assertEqual(r["p50"], 100.0)
        self.assertEqual(r["max"], 900.0)

    def test_too_few_frames_raises_rather_than_reporting(self):
        # A near-empty run means something broke upstream. Reporting a verdict
        # from 3 samples would be worse than refusing.
        with self.assertRaises(ValueError):
            t1.evaluate(samples(3, 100.0), samples(3, 50.0), 3, 30.0)

    def test_pinned_configuration_matches_the_spec(self):
        # If someone "optimises" these to make the gate pass, the measurement
        # stops describing the thing being shipped.
        self.assertEqual(t1.NUM_POSES, 2, "must match the browser's MAX_POSES")
        self.assertEqual(t1.CAPTURE_SIZE, (640, 480))
        self.assertEqual(t1.CONFIDENCE, 0.5)
        self.assertEqual(t1.GATE_P95_MS, 400.0)
        self.assertEqual(t1.GATE_MIN_FPS, 3.0)


if __name__ == "__main__":
    unittest.main()
