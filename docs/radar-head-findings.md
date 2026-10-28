# Radar head: already works, no app code needed

Confirmed on hardware 2026-10-02.

## The request

"Add a button to toggle the radar head attachment. If the radar head is attached, the servo has the
5th servo. It can rotate the radar head to the same side that the body is leaning based on the
human's left or right movement."

## The finding

**This is already what the firmware does.** No browser change is needed, and none was made. The
branch `feature/radar-head` contains this document and nothing else.

The fifth servo is **joint 0, head pan, ±90°**. Quaddle's joint map (`OpenCat.h:1120-1130`):

```c
// 关节0(头部左右): Head panning (±90 deg)
int angleLimit[][2] = {{-90, 90}, {-85, 85}, {-230, 70},{-230, 70}, {-50, 250}, {-50, 250}};
//                      joint 0     joint 1    joint 2/3 front legs   joint 4/5 back legs
```

Body Follow streams `ve` + `J`. That lands in `doSyncBody` (`display09tft.h:3692`) →
`reactionApplyRstickFromEyeNorm(eyeX, eyeY)` (`joystick.h:194`) →
`reactionRstickToJointValues(...)` → `reactionApplySimultaneousRstickJoints(j0, v2, v3, v4, v5)`.

And `joystick.h:59`:

```c
int j0 = -hx;   // head pan is the negated horizontal stick
```

So joint 0 is applied **in the same call as the four leg joints, from the same `hx`**. The head
pans to the side the body leans by construction, which is exactly the requested behaviour. At the
deadband (`|hx| <= 2 && |rsy| <= 2`) `j0` is forced to 0, so the head centres when you are centred.

Verified on the robot: `ve`, then `bytes:[74,114,40,0,126]` and `bytes:[74,114,-40,0,126]` pan the
head either way, and `bytes:[74,114,0,0,126]` centres it.

## Why the toggle cannot be a browser button

`reactionApplySimultaneousRstickJoints` writes head and legs together in one call. There is no host
token that asks for legs-without-head on this path. The firmware does have the variant —
`reactionApplyRstickLegsFromEyeNorm`, commented *"Legs only — keep sensor/PID head (joint 0)
unchanged"* — but it is selected inside `doSyncBody` only when the sensor head is active and the
joystick is not. A browser button cannot reach it.

**So suppressing head motion while keeping the lean is a firmware change, not an app change.** If
that is ever wanted, the smallest version is a new view sub-token that selects the Legs-only
variant, which belongs with the `vk` lease work already listed in `docs/body-follow-todos.md`.

What the app *can* already do: `EYE_TUNE.gain` scales `hx`, so it scales head pan, body lean and
pupil travel together. There is no way to scale them independently from the host.

## Disposition

Nothing to build. This branch exists only to record the investigation. Delete it whenever, or keep
it so the next person who wants a radar-head toggle finds this first.
