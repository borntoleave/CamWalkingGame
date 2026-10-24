"""Pure decision layer: Gemma's text in, robot wire bytes out.

No camera, no serial, no HTTP, no clock. That is the point: everything in here
is testable on a laptop, and `test_behaviour.py` pins it to exact bytes.

Two rules govern this file.

**Default deny.** Gemma's reply is untrusted text from a 2.3B model. It becomes
a command only by an exact, word-boundary match against ALLOWED_SKILLS.
Anything else returns None and the robot stays still. A dull demo is a fine
outcome; a robot acting on a hallucinated gait name is not.

**Bounded gaits only.** `k<skill> <cycles>` is terminated by the FIRMWARE
(app/index.html:6351-6360). That is what makes a multi-second inference loop
safe: if this process dies between decisions, the robot has already stopped.
Never emit a skill without a bounded argument.
"""

import re

# Baud for the Quaddle's USB CDC-ACM port, matching the browser.
BAUD = 115200

# The ONLY skill names this project has run on hardware
# (app/index.html:6141-6143: walkFwd "wkF", walkBack "wkB", walkStop "up").
#
# Instinct_Quaddle.h has many more (vtL, sit, hi, str). They are deliberately
# absent. The turn-gait table lists only `L` variants and the right-hand name
# has to be confirmed on hardware rather than guessed, and this project has
# already been bitten once by inferring a joint mapping from a comment: it made
# the robot hop instead of lean. Verify on the bench, then add here.
ALLOWED_SKILLS = ("wkF", "wkB", "up")

# Gait cycles, not milliseconds. reaction.h treats an argument below 200 as a
# cycle count and 200 or above as milliseconds, so staying well under 200 keeps
# the unit unambiguous. Three cycles is roughly a second of walking.
DEFAULT_CYCLES = 3
MAX_CYCLES = 199

# Lowercase ASCII command, params space-joined, newline appended by the sender
# (encodeCommand at :3385-3394, send() at :4574-4586). Binary uppercase tokens
# use a 126 terminator instead; nothing here emits those.
STOP_BYTES = b"kup\n"

# Case-insensitive so a shouting model still works, but \b anchors both ends:
# a substring match would fire "up" inside "upgrade" and "wkF" inside "wkFoo".
_SKILL_RE = re.compile(r"\b(" + "|".join(ALLOWED_SKILLS) + r")\b", re.IGNORECASE)

# Lowercase name -> canonical name. The wire format is case-sensitive.
_CANONICAL = {s.lower(): s for s in ALLOWED_SKILLS}


def decide(reply):
    """Model text -> (skill, cycles), or None to do nothing.

    Returns None for anything that is not exactly one allow-listed skill:
    refusals, prose, invented gaits, non-strings, and replies naming two
    DIFFERENT skills. That last case matters. A model that wrote "I could wkF
    or wkB here" listed its options instead of choosing, and resolving that by
    taking the first match is how a demo walks off a table. The same skill
    repeated is not ambiguous, just verbose, and is accepted.
    """
    if not isinstance(reply, str):
        return None

    found = {_CANONICAL[m.group(1).lower()] for m in _SKILL_RE.finditer(reply)}
    if len(found) != 1:
        return None

    return found.pop(), DEFAULT_CYCLES


def encode_skill(skill, cycles):
    """(skill, cycles) -> the exact bytes the browser's send() would write.

    Re-checks the allow-list rather than trusting its caller: `decide` is the
    gate, but this function is the one next to the serial port, and the cost of
    being wrong here is mechanical.

    `cycles` is clamped into 1..MAX_CYCLES. A non-positive or missing value
    falls back to DEFAULT_CYCLES instead of being dropped, because a skill sent
    with no argument runs UNBOUNDED, which is the single failure mode this
    design exists to avoid.
    """
    if skill not in ALLOWED_SKILLS:
        raise ValueError(f"refusing to send an unverified skill: {skill!r}")

    if skill == "up":
        # Stand is a posture, not a gait. A cycle count is meaningless.
        return STOP_BYTES

    try:
        n = int(cycles)
    except (TypeError, ValueError):
        n = DEFAULT_CYCLES
    if n <= 0:
        n = DEFAULT_CYCLES
    n = min(n, MAX_CYCLES)

    return f"k{skill} {n}\n".encode("ascii")


# The prompt. Kept here rather than in the loop so it is version-controlled
# next to the allow-list it has to agree with.
#
# Written for a 2.3B model: the task is stated once, the vocabulary is closed
# and tiny, and "answer with one word" is repeated at the end because that is
# the instruction small models drop first. The whitelist in `decide` is what
# actually enforces this, so a prompt that drifts costs a dull frame, not a
# runaway robot.
SYSTEM_PROMPT = """You control a small four-legged robot. You see one photo.

Reply with exactly ONE of these words and nothing else:

wkF - the person is far away, or waving you over, or beckoning
wkB - the person is very close, or pushing a hand toward you
up  - anything else, including an empty room

Answer with one word only."""
