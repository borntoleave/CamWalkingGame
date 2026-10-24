"""Contract tests for the Gemma-to-robot seam.

Run from the repo root on a laptop. No Pi, no robot, no model:

    python3 -m unittest discover -s pi5 -p 'test_*.py' -v

Why these exist. Gemma's reply is untrusted text from a 2.3B model that will
sometimes write a sentence, sometimes refuse, and sometimes invent a gait name.
The only thing between that text and the leg servos is `decide()`. A leak here
moves a real robot, so the interesting cases are all the ways a reply can fail
to be a command.

The assertions are on EXACT WIRE BYTES, not on shapes, because the consumer is
the ESP32-S3 firmware and it reads bytes. The byte format is pinned against
app/index.html: `encodeCommand` (:3385-3394) joins lowercase params with a
space, and `send()` (:4574-4586) appends the newline.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import behaviour as b


class TestWireFormat(unittest.TestCase):
    """Byte-level parity with what app/index.html puts on the wire."""

    def test_bounded_gait_matches_the_browser_byte_for_byte(self):
        # eyeSendSkill("wkF", 3) -> encodeCommand("k", ["wkF 3"]) -> "kwkF 3"
        # -> send() appends "\n". This is the whole contract.
        self.assertEqual(b.encode_skill("wkF", 3), b"kwkF 3\n")

    def test_skill_without_an_argument_has_no_trailing_space(self):
        # encodeCommand returns the bare token when params is empty, so a
        # stray space here would be a divergence from the browser.
        self.assertEqual(b.encode_skill("up", None), b"kup\n")

    def test_stand_helper_is_the_stop_command(self):
        self.assertEqual(b.STOP_BYTES, b"kup\n")

    def test_newline_is_the_only_terminator_no_tilde(self):
        # 126 ('~') terminates BINARY uppercase tokens only. Appending it to a
        # lowercase ASCII command would corrupt the frame.
        out = b.encode_skill("wkF", 3)
        self.assertNotIn(126, out)
        self.assertTrue(out.endswith(b"\n"))
        self.assertEqual(out.count(b"\n"), 1)


class TestDecideAcceptsRealModelReplies(unittest.TestCase):
    """The happy paths, in the messy forms a small model actually emits."""

    def test_bare_token(self):
        self.assertEqual(b.decide("wkF"), ("wkF", b.DEFAULT_CYCLES))

    def test_token_with_surrounding_prose(self):
        # Small models love a preamble. The token is still unambiguous.
        got = b.decide("The person is waving, so I will walk forward: wkF")
        self.assertEqual(got, ("wkF", b.DEFAULT_CYCLES))

    def test_token_with_markdown_and_whitespace(self):
        self.assertEqual(b.decide("  **wkB**  \n"), ("wkB", b.DEFAULT_CYCLES))

    def test_case_is_respected_for_the_skill_name(self):
        # OpenCat skill names are case-sensitive on the wire; "wkf" is not a
        # skill. But a model shouting the right name should still work.
        self.assertEqual(b.decide("WKF"), ("wkF", b.DEFAULT_CYCLES))

    def test_every_allowed_skill_round_trips_to_bytes(self):
        for name in b.ALLOWED_SKILLS:
            skill, arg = b.decide(name)
            self.assertEqual(skill, name)
            wire = b.encode_skill(skill, arg)
            self.assertTrue(wire.startswith(b"k"), name)
            self.assertTrue(wire.endswith(b"\n"), name)


class TestDecideRejects(unittest.TestCase):
    """Default-deny. These are the cases that keep the robot still."""

    def test_unknown_gait_is_refused(self):
        # vtL is a real firmware gait but UNVERIFIED by this project, so it is
        # deliberately not on the allow-list. A real name is not a safe name.
        self.assertIsNone(b.decide("vtL"))

    def test_invented_gait_is_refused(self):
        self.assertIsNone(b.decide("doBackflip"))

    def test_refusal_text_is_refused(self):
        self.assertIsNone(b.decide("I cannot determine what the person is doing."))

    def test_empty_and_whitespace_are_refused(self):
        for junk in ("", "   ", "\n\n", None):
            self.assertIsNone(b.decide(junk), repr(junk))

    def test_two_different_skills_in_one_reply_is_refused(self):
        # Ambiguity must not resolve to "pick the first one". A model that
        # listed its options did not make a decision, and guessing which half
        # it meant is how a demo walks off a table.
        self.assertIsNone(b.decide("I could wkF or wkB here"))

    def test_the_same_skill_repeated_is_still_accepted(self):
        # Not ambiguous, just verbose. "wkF. Yes, wkF." is one decision.
        self.assertEqual(b.decide("wkF. Yes, wkF."), ("wkF", b.DEFAULT_CYCLES))

    def test_skill_name_embedded_in_a_longer_word_is_refused(self):
        # A substring match would fire on "upgrade" or "wkFoo". Word
        # boundaries are what make the allow-list an allow-list.
        for junk in ("upgrade the firmware", "wkFoo", "backup"):
            self.assertIsNone(b.decide(junk), junk)

    def test_non_string_input_is_refused_not_raised(self):
        # The HTTP layer can hand us whatever JSON came back. A crash in the
        # loop is a robot left mid-gait, so refuse instead.
        for junk in (42, [], {}, object()):
            self.assertIsNone(b.decide(junk), repr(junk))


class TestCyclesAreBounded(unittest.TestCase):
    """The firmware ends the gait, but only if the argument stays a cycle count."""

    def test_default_is_a_cycle_count_not_milliseconds(self):
        # reaction.h: an argument below 200 is gait cycles, 200 or above is
        # milliseconds. Crossing 200 silently changes the unit, so the default
        # must stay well clear of that boundary.
        self.assertLess(b.DEFAULT_CYCLES, 200)
        self.assertGreater(b.DEFAULT_CYCLES, 0)

    def test_argument_is_clamped_below_the_millisecond_boundary(self):
        self.assertEqual(b.encode_skill("wkF", 10_000), b"kwkF 199\n")

    def test_zero_and_negative_arguments_fall_back_to_the_default(self):
        # An unbounded gait is the one thing this design must never emit.
        expected = b"kwkF " + str(b.DEFAULT_CYCLES).encode() + b"\n"
        self.assertEqual(b.encode_skill("wkF", 0), expected)
        self.assertEqual(b.encode_skill("wkF", -5), expected)

    def test_encode_refuses_a_skill_that_is_not_allow_listed(self):
        # Belt and braces: decide() is the gate, but encode_skill is the thing
        # holding the serial port, so it does not trust its caller either.
        with self.assertRaises(ValueError):
            b.encode_skill("vtL", 3)
        with self.assertRaises(ValueError):
            b.encode_skill("rm -rf /", 3)


class TestPinnedConfiguration(unittest.TestCase):

    def test_allow_list_holds_only_skills_verified_in_this_repo(self):
        # app/index.html:6141-6143 is the entire set of skill names this
        # project has run on hardware. Adding an untested name here is a
        # hardware change disguised as a string edit: do it on the bench
        # first, then in this test, then in behaviour.py.
        self.assertEqual(set(b.ALLOWED_SKILLS), {"wkF", "wkB", "up"})

    def test_baud_matches_the_browser(self):
        self.assertEqual(b.BAUD, 115200)


if __name__ == "__main__":
    unittest.main()
