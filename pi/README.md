# camWalk on a Raspberry Pi Zero 2 W

Setup guide. Everything here is a prerequisite for **T1**, the latency gate that decides whether
this project continues. Nothing in `pi/` runs the robot yet; only this document exists so far.

Spec: `docs/superpowers/plans/2026-10-09-pi-zero-camwalk.md`.

> **These commands come from documentation, not from a run on this hardware.** Nobody has executed
> them on a Pi yet. Where something is likely to differ, it says so.

## What v1 does, and does not

v1 is **aim-only**. The robot watches a person: the pupils track them and the body leans toward
them. It does **not** step and it does **not** turn, so **it does not follow anyone**. A person
walking sideways leaves the camera's view and is not recovered.

That is deliberate. The controller being ported has no steering, and the ~7° body lean cannot
re-point a camera bolted to the chassis. Steering is milestone 2.

## Hardware

- Raspberry Pi Zero 2 W (the "2 W", not the original Zero — the original's ARMv6 core has no
  MediaPipe builds)
- Pi camera, ribbon to the Zero's CSI connector (the Zero uses the narrower cable than a Pi 4)
- USB cable from the Pi to the Quaddle's USB port, for serial at 115200
- A microSD card, 16GB or more

Two things to settle on the bench before writing code:

1. **Power topology.** Does the Pi run off the robot's battery or its own supply? This is `U1` in
   the spec and it changes nothing about the code, but it tells you which failure you are exposed
   to. Note that a shared battery does **not** guarantee the Pi and the servos die together: the
   Pi can brown out at a higher voltage and leave the robot holding its last lean.
2. **Camera mounting.** The spec assumes the camera is on the **body/chassis**, not the head. If it
   ends up on the head, the control loop gain analysis is wrong by roughly 7x and the spec needs
   revisiting before you tune anything.

## 1. Operating system

**Raspberry Pi OS Bookworm, 64-bit.** This is not a preference.

Debian Trixie ships Python 3.13. MediaPipe supports Python ≤ 3.11, while picamera2 on Trixie builds
against 3.13, so the two cannot coexist there. Bookworm's Python 3.11 runs both. There is also a
reported picamera2 memory-allocation failure on the Zero 2 W under Trixie that does not occur on
Bookworm.

Flash with Raspberry Pi Imager, choosing **Raspberry Pi OS (64-bit)**, Bookworm. Set the hostname,
your user, and WiFi credentials in the Imager's settings so the Pi joins your network on first
boot; you will switch it to access-point mode later.

```bash
cat /etc/os-release          # expect VERSION_CODENAME=bookworm
uname -m                     # expect aarch64
python3 --version            # expect 3.11.x
```

If `uname -m` says `armv7l` you have the 32-bit image. Reflash; do not try to work around it.

## 2. Swap

512MB is not enough headroom for MediaPipe. Raise swap to 1GB:

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
free -h                      # expect ~1.0Gi of swap
```

**Swap here is an OOM-kill safety net, not headroom.** If MediaPipe actually pages during inference
the frame rate collapses, because the backing store is an SD card. The status page will report
swap-in rate for exactly this reason: sustained paging is a failure signal, not normal operation.

## 3. Camera

Bookworm auto-detects the camera; there is no `raspi-config` camera toggle any more.

```bash
rpicam-hello --list-cameras     # the camera should be listed
rpicam-hello -t 2000            # 2 second preview, or no output over SSH
```

If it is not listed, reseat the ribbon. The Zero's CSI connector takes the narrow cable and the
contacts face the board.

## 4. Python environment

picamera2 comes from **apt**, because it depends on libcamera, which cannot be pip-installed.
MediaPipe comes from **pip**. Bookworm blocks pip from touching system Python (PEP 668,
`externally-managed-environment`), so the two meet in a venv created with `--system-site-packages`:

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-venv git

cd ~
python3 -m venv --system-site-packages camwalk-env
source camwalk-env/bin/activate
pip install --upgrade pip
pip install mediapipe pyserial
```

`--system-site-packages` is the part that matters. A plain venv cannot see the apt-installed
picamera2, and `pip install picamera2` does not work because libcamera is not a pip package.

Expect the MediaPipe install to take a while on this board and to use the swap you just configured.

## 5. Smoke test

This is the gate before T1. Both libraries must import in **one** interpreter, the camera must
produce a frame, and the model must load.

```bash
source ~/camwalk-env/bin/activate
cd ~/CamWalkingGame            # wherever you cloned it, see section 7

python3 - <<'PY'
import sys, time
print("python", sys.version.split()[0])

import mediapipe as mp
print("mediapipe", mp.__version__)

from picamera2 import Picamera2
print("picamera2 imported")

import serial
print("pyserial", serial.__version__)

cam = Picamera2()
cam.configure(cam.create_preview_configuration(main={"size": (640, 480)}))
cam.start(); time.sleep(1)
frame = cam.capture_array()
print("frame", frame.shape)
cam.stop()

from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
opts = vision.PoseLandmarkerOptions(
    base_options=mp_python.BaseOptions(
        model_asset_path="app/vendor/mediapipe/models/pose_landmarker_lite.task"),
    running_mode=vision.RunningMode.VIDEO,
    num_poses=2,
    min_pose_detection_confidence=0.5,
    min_pose_presence_confidence=0.5,
    min_tracking_confidence=0.5)
with vision.PoseLandmarker.create_from_options(opts) as lm:
    print("model loaded")
print("SMOKE TEST PASSED")
PY
```

`num_poses=2` matches the browser's `MAX_POSES` and is what makes person-switching possible at all.
It costs inference time. If T1 shows it is unaffordable, dropping to 1 removes person switching and
is a scope change, not a tuning tweak.

If this fails, stop here and report the error. Every later step assumes it passed.

## 6. Serial to the robot

USB, not the GPIO UART. The Quaddle's ESP32-S3 has its spare UART wired to the voice module
(`SERIAL_VOICE`), so the GPIO route collides with it. USB at 115200 is the same transport the
browser already uses.

Find a stable device path. The `/dev/ttyUSB0` style name can change between boots:

```bash
ls -l /dev/serial/by-id/
```

Use the `/dev/serial/by-id/...` symlink in the config, never the bare `ttyUSB0`/`ttyACM0`. Which of
those two appears depends on whether the S3 enumerates natively or through a bridge chip; the
`by-id` path makes it moot.

Add yourself to the dialout group so the service can open the port without root:

```bash
sudo usermod -aG dialout $USER     # log out and back in for this to take effect
```

Manual check that the robot is listening, once `pi/robot.py` exists. Until then you can confirm the
link with any serial terminal at 115200: sending `kup\n` should make the robot stand.

## 7. Getting the code onto the Pi

```bash
cd ~
git clone https://github.com/borntoleave/CamWalkingGame.git
cd CamWalkingGame
git checkout feature/pi-zero
```

The vendored model (`app/vendor/mediapipe/models/pose_landmarker_lite.task`, 5.8MB) comes with the
clone, so there is nothing extra to download.

To update later: `git pull` while the Pi is in client mode (see below).

## 8. Access point mode

For tuning you open a page served by the Pi from your phone. Rather than putting the robot on a
venue's WiFi and hoping nobody finds the port, the Pi hosts **its own** WPA2 network. The WiFi
password becomes the access control and the traffic is encrypted.

Bookworm uses NetworkManager, so this is one command:

```bash
sudo nmcli device wifi hotspot ssid quaddle password CHOOSE-A-PASSWORD
nmcli device wifi show-password        # shows the SSID, password and a QR code
```

Your phone joins that network and reaches the Pi at its gateway address.

**While hosting, the Pi has no internet.** To `git pull` or `apt`, switch back:

```bash
sudo nmcli connection down Hotspot
sudo nmcli connection up <your-home-wifi-name>
```

Running as an access point and a client at the same time on the single radio needs a virtual
interface and is reported as fragile. Treat it as one mode or the other.

## 9. Running T1

T1 is the kill gate. It measures **capture-to-write latency**, not average frame rate, because a
loop can hold a healthy average while acting on observations hundreds of milliseconds old.

**Gate: p95 capture-to-write ≤ 400ms and sustained ≥ 3fps**, measured with the configuration in
section 5 and a synthetic CPU load standing in for the web server. Below that, the project stops
rather than continuing on a loop that cannot close.

The probe does not exist yet. It is the first thing to build.

Honest limitation: write-return is not mechanical response. The servo and firmware latency past
that point is unmeasured, which is part of why the loop gain is set empirically on the floor rather
than calculated.

## 10. What this setup does not cover

Two failure modes stay open and neither can be fixed from the Pi:

- **A dead Pi cannot send zeros.** The firmware holds the last stick value until power cycle. Clean
  stops and restarts are handled, but a freeze, a yanked cable or a brownout leaves the robot
  holding a lean until you cut power.
- **The leg guard can lapse.** `viewMode == 3` is the only thing keeping the gaze stream out of the
  leg servos, and it is refreshed every 5 seconds. Anything that changes the view in between lets
  the next packet reach the legs. There is no read-back, so the Pi cannot detect it.

Both need a firmware command lease (the `vk` token in `docs/body-follow-todos.md`), which is out of
scope here. Neither is new: both are inherited from the browser build.
