# Quaddle + Raspberry Pi Zero 2 W — demo concepts

**Date:** 2026-11-02 (rewritten; first draft was a list of obvious ideas)
**Grounding:** measured numbers from `docs/camwalk-hardware-findings.md`, the
command surface in `app/index.html`, and the research in §8.

---

## 1. Thesis: perform the latency, do not hide it

The first version of this document treated 2.6 fps and 500ms inference as
problems to engineer around. That was the wrong instinct, and two findings say
so.

**Failure is the show.** Boston Dynamics' kicked BigDog has 17M views. The
humanoid that reacted to a starting gun by lying down and staring at the sky was
the breakout character of the 2026 World Humanoid Games. Showing robots as
clumsy and a little stupid *puts people at ease*; obsessively stage-managed
demos do the opposite.

**A simple drawn face is enough.** Emotional expression in **simple line
drawings** of a robot's face elicits the same response from humans as human
telepresence, and people prefer to play games with a robot that shows sentiment.
The Quaddle has a TFT with drawn eyes. It is the highest-leverage unused
hardware on the robot, and the research says it does not need to be
sophisticated to work.

Put together: **a robot that visibly thinks, hesitates, gets confused, and shows
all of it on its face is more engaging than one that performs flawlessly.** The
500ms inference is not dead time. It is a beat of visible thought, and this
board gives you one for free whether you want it or not.

Every idea below is scored on that basis.

### What the hardware actually gives you

| Lever | Reality | Used today |
|---|---|---|
| TFT eyes (`v`) | Drawn face, research-backed as sufficient | Barely |
| **Joint 0 head pan, ±90°** | Fast, decoupled from the body | **Never** |
| `I` binary | Direct per-joint angles, arbitrary poses, no firmware work | Legs only |
| `k<skill> <n>` | Bounded gait, **firmware-terminated** | Yes |
| Audio in | **Real time** (wake word RTF 0.053) | **Never** |
| Vision | 2.6-2.9 fps, 153ms fixed overhead | The failed loop |
| `J` | Held until changed — needs a live host | Yes, and it is the risky one |

The two never-used levers — **the head joint and audio** — are the two fastest
things on the robot. The project spent two months on the slowest.

---

## 2. Tier 1 — the strong ones

### 1.0 Pushups together

You and the robot do pushups side by side. It counts, it keeps score, it gets
tired, and eventually it gives up.

**Why the camera mounting finally helps.** A chassis-mounted camera at floor
level is bad at looking at standing humans, which has been this project's core
framing problem throughout. A person in a pushup position is **horizontal, at
floor level, directly in front of the robot, and close enough to fill the
frame**. The low mount and the 120 degree lens stop being limitations and become
correct. No other idea on this list turns that constraint around.

**Why it beats the 2fps problem by construction.** Rep detection is a threshold
crossing, not tracking. But at 2.6 fps a 1.5s rep gives roughly two frames per
phase, and faster reps would alias exactly like gait shake. The fix is to
**invert who leads: the robot sets the tempo and you follow it**. The thing
doing the sampling chooses the rate, so the aliasing problem cannot arise. The
robot is the metronome.

**Why it travels.** It has an emotional arc rather than just rules. The robot
slows, shakes, shows strain on the TFT eyes, and collapses. Per the virality
research in section 8, a robot giving up first is better content than a robot
winning. It needs no explanation in any language, and it reads in a three second
clip.

**Why it is a product and not only a demo.** A desk companion that works out
with you is an existing category people already buy into.

**Build:** `I` direct joint angles on 2-5, flexed together. This is a direct
extension of working code: the browser app already maps finger bend onto those
same four joints within `ANGLE_RANGE = 25`. Check `Instinct_Quaddle.h` for an
existing pushup skill on the bench rather than guessing the token.

**Gating risk, test this first.** MediaPipe pose is trained overwhelmingly on
upright people, and a human in plank is out of distribution. This project has
already measured what that costs: an inverted subject dropped detection from 98%
to 79%. Horizontal is likely worse.

```bash
python3 pi/t1_latency.py --seconds 30 --rot180 --poses 1
```

Do reps in frame for the full 30s and read the `detected` percentage. Above ~90%
this works as designed. Below ~70% it needs a cruder signal than full pose,
such as vertical motion of whichever landmarks survive.

**Smaller unknowns:** servo thermal and battery load under repeated full-range
flexion bearing body weight, and whether plus or minus 25 degrees produces a
visually legible pushup or needs more travel than the app currently allows.

### 1.1 Startle, flinch, and boredom: reflexes, not cognition

Not a demo on its own. The substrate everything else sits on.

A loud sound or sudden motion makes the robot **flinch** — a fast head snap plus
an eye change, under 100ms, no inference involved. Nothing happening for two
minutes makes it **look around, settle, and sigh**. Someone approaching makes it
**perk up**.

**Why it matters more than it sounds:** idle and reflex behaviour is what makes
a robot read as alive. It is nearly free, it never fails, and it fills every gap
while slower systems think. A robot that sits perfectly still between commands
reads as a machine; one that fidgets reads as a creature.

**Cost:** low. Audio threshold or frame differencing, head joint, eye mode.
**Latency exposure:** none. This is the one thing on the board that is fast.

### 1.2 Red light, green light

The robot turns its head away (joint 0, ±90°). You advance. It turns back and
compares frames. Caught anyone moving? It reacts — and sends them back.

**Why it is the best fit on the board:** the game is **turn-based**, so latency
is structurally irrelevant. More than that, the rules *require* the robot to not
be looking half the time, which is exactly what a 2fps camera wants. Comparing
two still frames for motion is trivial compared to tracking.

**Why it travels:** it is a social game between a robot and a room full of
people, it is instantly legible with no explanation, and it is already a shared
cultural reference. When the robot gets it wrong, that is the funny part — which
the virality research says is the point, not the failure.

**Cost:** low-moderate. Head pan, frame differencing, eye expressions, a bounded
gait for the reaction. No tracking, no control loop.

### 1.3 Sound-seeking head

Clap, and the robot snaps its head toward you.

**Why this is the highest impact per hour of work on the list:** it combines the
only real-time capability the board has with the only fast actuator nobody uses.
A head that turns toward sound within 100ms is startlingly lifelike, and it
costs no inference at all. Compare that to two months spent trying to make a 7°
body lean track a person.

**Cost:** low, *once the microphone exists*. Direction-of-arrival needs two
mics; one mic gives presence and triggers a scan instead.
**Blocked by:** the audio BOM gap (§7).

### 1.4 The thinking face

Wire the TFT eyes to the robot's **actual internal state**: scanning, found you,
lost you, confused, thinking. The 500ms inference becomes a visible pause with a
face on it.

**Why it is the cheapest upgrade available:** every other demo gets better the
moment the robot's state is legible. It turns the board's weakness into
characterisation, and the research says a simple drawn face is sufficient.

**Honest version:** when the model is unsure, *show uncertainty* rather than
faking confidence. A robot that squints and gets it wrong is more likeable and
more honest than one that pretends.

**Cost:** low. Mostly a mapping from existing state to `v` modes.

### 1.5 Copy me

You strike a pose. The robot maps it onto four legs and a head, and holds it.

**Why it fits:** held poses make latency irrelevant — nobody minds waiting a
second for the robot to work it out. It uses `I` for direct joint angles, so no
firmware work at all.

**Why it is interesting rather than generic:** mapping a bipedal human pose onto
a quadruped is a genuinely unsolved little problem with no correct answer. The
failures are charming, legible and funny, and people immediately start trying to
break it. That is engagement, not a bug.

**Cost:** moderate. Pose landmarks already run. The mapping is the creative work.

### 1.6 Paper-card programming

Lay printed cards on the floor: forward, turn, repeat. The robot walks the line,
reads each card as it reaches it, and executes.

**Why it is not just KUBO or Botley again:** those use proprietary RFID tiles or
colour sensors on wheeled toys for ages 4-8. **A camera reading printed paper
means the consumables cost nothing** — print more cards, invent new ones,
localise them, let students design their own. And the thing executing is a
walking quadruped, not a wheeled puck.

**Why vision at 2fps is fine:** reading a card is a discrete event at a known
moment, not a tracking problem. Stop, look, decide, walk a bounded burst, repeat.

**Strategic fit:** there is **no Quaddle curriculum as of 2026-11-01** — Petoi's
curriculum pages cover Bittle and Nybble. This is open ground, and screen-free
coding is a category parents actively search for.

**Cost:** moderate. ArUco markers are the robust choice over custom symbols.

---

## 3. Tier 2 — strong, longer, or riskier

### 2.1 Robot sees robot

Two Quaddles that detect each other and react. Approach, mirror, retreat,
circle. No human in the loop.

**Why it is worth building:** two slow agents reacting to each other produce
emergent behaviour that neither was programmed with, and watching robots deal
with each other is a different and more durable kind of interesting than
watching one obey a person. It also makes the case for owning two.

**Cost:** moderate, plus a second robot and Pi.
**Unverified:** how reliably a Quaddle recognises another Quaddle at floor level.

### 2.2 The robot's diary

It logs what it saw all day. At the end, a small language model turns the log
into a short first-person account. *"Someone new came in around two. I lost
track of them behind the chair."*

**Why latency does not matter:** it runs once, overnight, with nobody watching.
This is the only shape in which a 135M-parameter model on a 512MB board makes
sense — and SmolLM2-135M is the community pick for exactly this board.

**Why it travels:** it produces a shareable artifact that persists after the
demo ends, and the robot's limited, slightly confused perspective is the charm
rather than a limitation to apologise for.

**Cost:** moderate. **Unverified:** SmolLM2 on this board; reported, not tested.

### 2.3 Desk companion that reacts to your builds

CI fails, the robot sulks. PR merged, it does a trick. Deploy goes out, it
watches the dashboard.

**Why it is a real product shape:** no camera, no ML, no latency exposure — just
a webhook and a personality. Developers are a large, vocal audience who buy
desk objects and post about them. It is also the lowest-effort idea here that
someone would actually pay for.

**Cost:** low.

### 2.4 Quaddle-cam

The robot walks a room slowly and records. The **footage** is the product: a
dog's-eye-level tracking shot of a space, or an overnight timelapse.

**Why slowness becomes an asset:** deliberate, steady motion is what a camera
dolly is *for*. Every other idea fights the board's pace; this one bills it as a
feature. Floor-level footage of ordinary rooms is genuinely unusual to look at.

**Cost:** low-moderate. **Caveat:** gait shake at 2-4Hz will need either
stabilisation or a stop-move-stop capture pattern.

### 2.5 Guess what I'm looking at

The robot displays what it thinks it sees. The audience sees how often it is
wrong, and how confidently.

**Why it earns its place:** it is honest AI education with the failures left in.
For a STEM company this is more valuable than a demo that hides its limits, and
it directly supports the "robots are clumsy and that is fine" framing that makes
this stuff likeable. It also needs almost no new code — the inference is already
running.

**Cost:** low.

---

## 4. Tier 3 — blocked or weak

| Idea | Status |
|---|---|
| Real-time tracking, ball chasing, "follow me" | **Measured impossible.** 2.6 fps, 4.4s tail. |
| On-board VLM scene understanding | Needs a Pi 5. Code on `feature/gemma-pi5`, never run. |
| Photo booth | Works, but not robot-specific — a tripod does it. Dropped from Tier 1. |
| Generic "it dances" | Every robot dances. Only interesting with reaction (§1.1) attached. |
| Voice assistant with a command list | Alexa did it. The *listening head* (§1.3) is the robot-native version. |
| SLAM / autonomous navigation | Far beyond this compute budget. |
| Cloud-dependent anything | Venue networks measured at 275 KB/s with client isolation. |

---

## 5. Ranked

| # | Demo | Why it wins | Effort | Risk |
|---|---|---|---|---|
| 1 | **Pushups together** (1.0) | Only idea where the floor-level camera is an asset. Robot-led tempo kills the fps problem. | Low-mod | **Pose detection on a horizontal human — test first** |
| 2 | **Reflexes and idle** (1.1) | Makes everything else feel alive. Never fails. | Low | None |
| 3 | **Red light, green light** (1.2) | Turn-based, so the board's weakness vanishes. Socially legible. | Low-mod | Low |
| 4 | **Sound-seeking head** (1.3) | Only real-time sense + only unused fast actuator | Low | BOM |
| 5 | **Thinking face** (1.4) | Cheapest upgrade; improves every other demo | Low | None |
| 6 | **Paper cards** (1.6) | Fills the Quaddle curriculum gap; zero-cost consumables | Mod | Low |
| 7 | **Copy me** (1.5) | Failures are the fun part | Mod | Low |

**Build 1.1 and 1.4 first regardless of what ships.** They are the substrate:
reflexes and a legible face make every other item on this list better, and
neither touches the slow path.

**The one to put in front of a camera: pushups.** It is the only idea here in
which the chassis-mounted floor-level camera is an advantage rather than the
thing to design around, and the only one with an emotional arc instead of a rule
set. Gated on one ten minute test.

**The one to show a crowd: red light, green light.** It is the only idea here
whose *rules* make a 2fps camera correct rather than merely tolerable.

**The one that is a product, not a demo: paper cards.** Open curriculum ground,
consumables that cost nothing, and a category parents already search for.

---

## 6. What to avoid

- **"It follows you."** The ~7°/joint lean cannot re-point a chassis camera, and
  without steering it does not follow. `pi/README.md` is explicit.
- **Streaming `J`.** Held by firmware until power cycle; a frozen host leaves a
  held lean. Prefer bounded `k<skill> <n>`, which the firmware ends itself.
- **Guessed gait names.** `Instinct_Quaddle.h` lists only `L` variants. Guessing
  the right-hand name once made this robot hop instead of lean.
- **Hiding the latency.** It will leak anyway. Give it a face instead.
- **Flawless stage-managed demos.** The research is unusually clear that they
  land worse than visible, likeable failure.

---

## 7. Gaps to close

1. **Audio hardware — the big one.** No mic, no audio out on a Zero 2 W. Needs a
   USB sound card or an I2S MEMS mic (INMP441). **Blocks 1.1 partially and 1.3
   entirely**, which are two of the top three. Direction-of-arrival wants two
   mics. Settle this first; it is cheap and it unlocks the board's only fast
   sense.
2. **Head joints 0 and 1.** ±90° pan, never used, central to four ideas above.
   Verify range, speed and whether it is audible — a loud servo changes which
   reflexes feel good.
3. **TFT eye modes.** The app only ever sends `ve`. Enumerate what the firmware
   actually offers before designing expressions around it.
4. **Turn gaits on hardware.** Right-hand variants unconfirmed. Needed by 1.6.
5. **The 2-4.4s tail stalls.** Unexplained. Harmless for event-driven work,
   fatal for anything timed.
6. **Power budget.** Camera plus inference plus servos on one battery, unmeasured.

---

## 8. Sources

Measured here: `docs/camwalk-hardware-findings.md`, `docs/pi-zero-t1-results.md`.

External, 2026-11-02:
- [Emotional expression in simple line drawings of a robot's face](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5439005/) — line-drawing faces match human telepresence; people prefer playing with expressive robots
- [Slate: on robots falling over, and why we like it](https://slate.com/technology/2026/09/world-humanoid-games-robot-olympics.html) — "failure is the show"; the shy robot; BigDog's 17M views
- [TechCrunch: how to fake a robotics demo](https://techcrunch.com/2024/02/09/how-to-fake-a-robotics-demo-for-fun-and-profit/) — what over-staged demos cost in credibility
- [Picovoice: speech recognition on Raspberry Pi](https://picovoice.ai/blog/speech-recognition-on-raspberrypi/) — real-time wake word on a Zero
- [Edge AI compute ladder](https://theaivibe.org/edge/edge-ai-compute-ladder-what-runs-on-every-board) — SmolLM2-135M as the Zero 2 W pick
- [Ozobot: screen-free coding](https://ozobot.com/blogs/news/screen-free-coding-for-kids) and [coding toys 2026](https://www.codingal.com/coding-for-kids/blog/coding-toys-for-kids-the-best-games-toys-and-apps-by-age-2026-guide/) — KUBO TagTiles, Botley, the proprietary-consumable model this would undercut
- [Petoi: Raspberry Pi robotics projects](https://www.petoi.com/blogs/blog/raspberry-pi-robotics-projects-with-petoi-open-source-quadruped-robots) and [docs: Pi serial interface](https://docs.petoi.com/apis/raspberry-pi-serial-port-as-an-interfac) — existing Pi material is plumbing only

Petoi's published Pi content is integration plumbing. No flagship camera demo
exists, and the curriculum covers Bittle and Nybble rather than Quaddle.
Everything in §2 and §3 is open ground.
