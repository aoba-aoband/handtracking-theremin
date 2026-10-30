# Handtracking Theremin — Quick Start

[日本語](QUICKSTART_ja.md) · [Project README](README.md) · [User Manual](USER_MANUAL.md)

For step-by-step playing instructions, see the [User Manual](USER_MANUAL.md). This Quick Start also includes information for the person setting up the app.

This guide uses the Regular UI with MediaPipe, OSC and SuperCollider on Windows
PowerShell. The separate sounddevice player is not part of this launch path.

## 1. First-time setup

You need Python, Git, SuperCollider, a webcam and an audio output. The development
environment verified so far is Python 3.10.8 and SuperCollider 3.14.1 on Windows.
Install SuperCollider before starting the UI. Automatic discovery checks
`C:\Program Files\SuperCollider*\sclang.exe`; see below for other locations.

For a new checkout:

```powershell
git clone https://github.com/aoba-aoband/handtracking-theremin.git
cd handtracking-theremin
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

The MediaPipe model is included at `models/hand_landmarker.task`. These commands
call the virtual environment's Python directly; activation and a PowerShell
execution-policy change are not needed.

If you already have this repository, use its existing folder and skip cloning.
An older local folder named `handtrack_music_platform` still works; the GitHub
rename does not require renaming it. Install the requirements again after an
update that changes dependencies.

## 2. Launch

From the repository root:

```powershell
.\venv\Scripts\python.exe main.py ui
```

1. Click **Start** or press **F5**. You do not need to open the SC IDE separately.
2. Wait while **Start pending** prepares SC and synchronizes settings.
3. Check for **SC connected**, **Camera running**, camera video and landmarks.
4. Show both hands. Raise / lower the right index finger for pitch; separate /
   bring together the left thumb and index finger to vary amplitude. Use the
   Left / Right detection labels to confirm routing. Raising the right middle
   fingertip above the index fingertip adds one octave.
5. **Stop / F6** mutes and stops the camera. **PANIC / F12** mutes immediately
   while keeping a running camera active. Use **Start / F5** to resume.

Startup pitch is 220–880 Hz before the octave gesture; Root A, Scale
`minor-pentatonic`, Quantize OFF. Expand Camera **Settings** to change it.
Choose Basic / Additive or Subtractive above Controls to change the complete
probe. After a probe switch or Patch recall, press Start to resume.

## 3. Save your work

- Enter a **Patch** name and click its **Save**. Select the name and **Recall**
  to restore both probes, pitch and mapping. Recall keeps Gate closed.
- Double-click panel titles to float Camera, Controls or Analysis; drag titles
  to dock them. Enter a **Layout** name and click its **Save** to preserve the
  arrangement separately. The last layout is also restored on the next launch.
- Parameter edits are not automatically restored on restart. Save a Patch for
  settings you want to keep. All saved data lives in local `user_data/`.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| UI will not open / missing `PySide6` or another module | Run the requirements install above with the same `venv` Python, then launch again. Check the console traceback. |
| Start pending does not finish | Inspect the status message and `logs/regular-sc.log`. SC startup is cancelled after 45 seconds. Check SC installation and audio-device errors. |
| SC connected, but no video | SC connection alone does not start the camera. Click Start; read any persistent **Camera error** above the preview. Close other camera users, then retry or select another index below. |
| Video works, but no sound | Check Gate is ON, Output Level and Amp Min / Max, hand detection, SC log and the system audio output. After PANIC / recall / probe switching, press Start again. |
| Filter / Envelope diagram moves while Scope is unavailable | Diagrams are calculation models. Scope needs a connected SC audio server; Monitor must be ON for current SC telemetry. |
| Hand routing or pitch looks wrong | Check Left / Right detection, octave gesture, Root / Scale / Quantize, and Min / Max in Camera Settings. Guide Mode changes the guide, not Quantize. |

To use a different camera, stop and close the current UI, then launch:

```powershell
.\venv\Scripts\python.exe main.py ui --camera-index 1
```

For SC installed outside automatic discovery, open the SC IDE and evaluate the
outer block in `sc/regular_bridge.scd`. Connect to that session's language port
(usually 57120), then click Start:

```powershell
.\venv\Scripts\python.exe main.py ui --ui-sc-port 57120
```

Regular UI normally uses 57121; the legacy CLI uses `config.py`, default 57120.
Closing the UI quits its own SC processes; externally opened SC stays open.

## CLI diagnostics

Run one camera user at a time. Stop the Regular UI camera first. Press `q` in an
OpenCV preview window to exit.

```powershell
.\venv\Scripts\python.exe main.py camera
.\venv\Scripts\python.exe main.py hands --show-features
```

For the legacy musical OSC route, first evaluate either `sc/basic_receiver.scd`
or `sc/subtractive_probe.scd` in the SC IDE, then run:

```powershell
.\venv\Scripts\python.exe main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel
```

Enable Gate in that probe's SC control window; Space toggles it when the SC
control window has focus. This is different from the Regular UI F5 / F6 / F12
controls. `--quantize-pitch` optionally enables quantization. Use
`.\venv\Scripts\python.exe main.py --help` for all flags.

For CLI performance logs and charts, with the chosen SC probe ready:

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
.\venv\Scripts\python.exe main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel --show-performance-stats *>&1 | Tee-Object -FilePath logs\perf.txt
.\venv\Scripts\python.exe tools\plot_perf_log.py logs\perf.txt --out-dir analysis\perf
```

This produces a summary CSV and timing / FPS PNGs. It measures performance;
it does not enable a low-latency mode. See [README](README.md#development-and-verification)
for automated and real-connection tests.
