# Handtracking Theremin

[日本語](README_ja.md) · [Quick Start](QUICKSTART.md) · [クイックスタート](QUICKSTART_ja.md)

A webcam-controlled theremin prototype. Python detects hands with MediaPipe,
converts their movement into musical control events, and sends OSC to
SuperCollider for sound synthesis. The current focus is a playable theremin;
tracking, features, mapping and output remain separate for future instruments.

## Start here

Use the [English Quick Start](QUICKSTART.md) for installation, first sound and
troubleshooting. On an existing checkout with dependencies installed, run this
from the repository root in PowerShell:

```powershell
.\venv\Scripts\python.exe main.py ui
```

Click **Start** or press **F5**. SC launches if necessary; **Start pending**
remains visible until connection and settings synchronization finish. The camera
then starts, and the performance gate opens after its first frame. **Launch SC**
prepares SC separately without starting the camera.

The development environment verified so far is Windows, Python 3.10.8 and
SuperCollider 3.14.1. The repository includes the MediaPipe model at
`models/hand_landmarker.task`. The UI and automatic SC discovery currently target
Windows; other operating systems have not been validated.

## Entry points

| Entry point | Purpose | Sound / OSC |
| --- | --- | --- |
| `main.py ui` | Regular UI: Camera, Controls, Analysis | SC bridge on `127.0.0.1:57121` by default |
| `main.py hands` | OpenCV landmark preview and mapping diagnostics | OSC only with `--send-osc`; target in `config.py`, default `57120` |
| `main.py camera` | Raw camera preview | None |
| `main.py` or `main.py osc` | OSC connectivity test | Generic test events to the target in `config.py` |
| `gui/theremin_gui.py` | Separate Tkinter / sounddevice player | Local audio; independent of SC probes and Regular UI patches |

Run `main.py --help` for CLI options. `hands` needs `--sample-mapping` to generate
musical events for the SC probes; generic `/hand/...` events alone do not play them.

## Regular UI

Camera, Controls and Analysis are independent dockable panels. Double-click a
panel title or use its Float button to detach it, then move or resize it, including
onto another monitor. Drag its title to dock it again. Panels are not hidden in
tabs. Camera **Settings** shows or hides the longer mapping and pitch controls.

| Action | Shortcut | Behavior |
| --- | --- | --- |
| Start | F5 | Waits for SC, starts the camera, then opens Gate; also resumes after PANIC |
| Stop | F6 | Cancels pending Start, mutes and stops the camera |
| PANIC | F12 | Mutes immediately and closes Gate; leaves a running camera active |

These shortcuts and buttons are available across the panels, including floating
ones. Space is not a performance shortcut in Regular UI. Patch recall, Reset
Defaults, reconnect and probe switching leave Gate closed; use Start to resume.

### Hands and pitch

| Input | Current sample mapping |
| --- | --- |
| Right index finger height | Exponential pitch mapping within Min / Max |
| Right middle fingertip above index fingertip | One octave up, before quantization |
| Left thumb–index distance (`pinch`) | Continuous amplitude control |
| Left index finger horizontal position | Hand Tone input in Subtractive Probe when enabled |
| Left pinch threshold and hysteresis | Articulation gate for Subtractive Probe when enabled |

Here `pinch` is normalized image-space distance: separating thumb and index
increases the value. It is not an inverse “pinch strength” or physical distance.
Check the Camera Left / Right detection labels when testing the mapping.

Root has all 12 pitch classes. Scale choices, in source order, are `chromatic`,
`major`, `minor`, `major-pentatonic`, `minor-pentatonic`. Guide Mode is `simple`,
`chromatic` or `scale`; Quantize is OFF / ON. Min and Max can each be set by note
(MIDI 0–127) or Hz, independently of Root and Scale, with Min < Max. The octave
gesture can raise the final pitch above the configured base range.

Startup defaults are Min 220 Hz, Max 880 Hz, Root A, Scale `minor-pentatonic`,
Quantize OFF and Guide Mode `simple`. Pinch gate defaults are on threshold 0.65,
off threshold 0.45 and hand-loss release 0.25 s. Regular UI mapping adjustments
can be saved in a Patch; no pitch-range calibration from hand height is provided.

### Probe selection and analysis

Select **Probe** above Controls to change the complete synthesis / processing
path. Each probe retains its own parameter bank within the session and in a Patch.

| Probe | Available processing |
| --- | --- |
| Basic / Additive | Base sine, 12 harmonics, response, portamento, soft clip, filter, delay, reverb |
| Subtractive | Osc 1 / Osc 2 (Saw, Pulse, Triangle), sub / noise, filter, key tracking, Hand Tone, articulation and filter envelope |

The source-derived catalogs currently contain 46 Basic and 41 Subtractive entries,
including readouts. Hover controls for formal SC parameter names. Articulation
and Filter Env default to OFF; the filter envelope requires both toggles ON.

Analysis uses SC-reported values such as `followedFreq` and `effectiveCutoff`.
Filter and envelope curves are labelled calculation models. **Open Scope** and
**Open FreqScope** open native SC views of the real signal. Disconnected or stale
monitor data is shown as unavailable. See the [Regular UI guide](gui/regular/README.md)
for the parameter contract and connection details.

### Patch and Layout

- **Patch**: enter a name and Save; select it and Recall to restore both probe
  banks, pitch and mapping. Recall keeps Gate closed.
- **Layout**: separately saves panel geometry, docking and Camera Settings
  visibility. The last layout is also restored on launch.
- Files are stored under `user_data/patches/`, `user_data/layouts/` and
  `user_data/session-layout.json`. These local files are ignored by Git.
- Parameter changes are not automatically restored after restart; save and recall
  a Patch. Layout recall does not change sound settings.

## SC connection and diagnostics

Regular UI launches its own `sclang` on language port **57121**, with a separate
automatically allocated `scsynth` audio-server port. `config.py` controls the
legacy CLI target, not the Regular UI port. For a manually managed SC session,
evaluate [sc/regular_bridge.scd](sc/regular_bridge.scd) and connect to its language
port, usually `57120`:

```powershell
.\venv\Scripts\python.exe main.py ui --ui-sc-port 57120
```

Closing Regular UI quits only SC processes it launched. An external SC session
receives PANIC but remains open. Run one performance sender per receiver.

The Regular UI bridge mutes after about 2 seconds without UI contact. Both probes
also release input after 1 second without left-pinch packets once pinch has been
received; the check runs every 0.1 seconds. Normal release times and FX tails can
apply to the input watchdog; Regular UI PANIC uses an immediate output mute.

For camera errors, SC startup timeout, or silence, follow the
[Quick Start troubleshooting](QUICKSTART.md#troubleshooting). The default SC log is
`logs/regular-sc.log`; custom ports use `logs/regular-sc-<port>.log`.

## Development and verification

```text
Camera → src/hand_tracker.py → src/features.py → src/mapping.py / src/pitch.py
       → OSC → sc/regular_bridge.scd → selected SC probe → audio output
```

Python owns pitch range, octave, scale and quantization; SC owns synthesis,
response, amplitude shaping and effects. `/hand/0` and `/hand/1` are detection
indexes, not persistent identities. Musical `/sample/right/...` and
`/sample/left/...` routing uses handedness with debounce, not full identity tracking.

| Location | Responsibility |
| --- | --- |
| `main.py`, `config.py` | Entry points and CLI / mapping defaults |
| `gui/regular/` | Qt panels, settings persistence, SC transport and camera worker |
| `src/` | Tracking, features, mapping, pitch and OSC output |
| `sc/basic_receiver.scd`, `sc/subtractive_probe.scd` | Probe parameters, DSP, receivers and cleanup |
| `tools/`, `tests/` | Catalog generation, verification and performance analysis |

Run automated tests from the repository root:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
& 'C:\Program Files\SuperCollider-3.14.1\sclang.exe' -D (Join-Path $PWD 'tests\sc_input_lifecycle.scd')
```

Adjust the SC executable path to your installation. The SC lifecycle test does
not need a camera or audio server. For an opt-in real SC / OSC check on port 57122:

```powershell
.\venv\Scripts\python.exe tools\verify_regular_connection.py
.\venv\Scripts\python.exe tools\verify_regular_connection.py --camera
```

These checks launch and close a separate muted SC server. `--camera` exercises
production Start / Stop and frame delivery; release the camera from other apps
first. Add `--scopes` to open native signal windows. Automated checks do not
replace listening or performance tests.

After editing SC parameter definitions, regenerate the validation table and run
the tests:

```powershell
.\venv\Scripts\python.exe tools\generate_regular_specs.py
```

For legacy CLI diagnostics and performance-log charts, see
[Quick Start: CLI diagnostics](QUICKSTART.md#cli-diagnostics). `logs/`, `analysis/`
and `user_data/` are ignored generated / local data directories.

## Limitations and design history

Tracking loss and handedness / detection-order changes can still cause jumps.
Listening and extended performance tests, native scope content inspection and
placement on a second physical monitor remain manual validation tasks. Hardware
behavior depends on the camera and SC audio device. Ableton / Max for Live
integration, a dedicated low-latency mode, LFO, PWM, unison and polyphony are not
implemented.

Previous development notes, including V2a decisions and future proposals, are
preserved in the [archived prototype notes](docs/archive/prototype-notes.md).
They describe historical experiments; this README and Quick Start describe the
current entry points.
