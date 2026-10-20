# Handtrack Music Platform

## Regular UI

Run `python main.py ui`, then click **Start**. It launches SC if needed and waits
for synchronization before opening the camera. Install the updated requirements first. Camera, Controls and Analysis
are dockable/floating panels; Patch and Layout are saved independently.
F5 starts, F6 stops, F12 panics. The existing CLI and sounddevice launcher remain
independent. See the [Regular UI guide](gui/regular/README.md) for setup, connection
ports, parameter contracts, verification and remaining hardware checks.

This project is a small platform for turning hand landmark data into generic
control events. It is not designed as a fixed theremin patch. The current goal
is to keep hand tracking, neutral features, event mapping, and output adapters
separate so SuperCollider, Ableton Live, Max for Live, or other systems can
interpret the same control stream differently.

Japanese quick start: [README_ja.md](README_ja.md)

## Prototype Status

This is a prototype / practice build, not a finished application. It is meant
to be playable enough for early rehearsal and feedback while the mapping,
tracking, sound, and settings ideas are still evolving.

The current UI is a temporary OpenCV trackbar panel. It is functional but not
final. Root, scale, quantization, guide mode, and pitch range can be changed
from the prototype panel without editing code or typing a long command every
time.

The main expected environment is currently Windows + Python + SuperCollider.

## V2a articulation decision

Current decision:

- Left-hand pinch has two simultaneous meanings:
  1. continuous amp control
  2. articulation gate source via threshold + hysteresis

Status:

- Provisional and reversible.
- This is a V2a sample-mapping experiment, not a platform-wide rule.

Why:

- Existing continuous expression is preserved.
- Onset and release can be explored without a separate gesture.
- The design suits a continuous-pitch instrument.

Alternatives intentionally deferred:

- Pinch controls amp only.
- Pinch controls gate only.
- Another gesture controls articulation.
- Python sends only raw pinch and SuperCollider derives the threshold gate.

Reversal point:

- `articulationOn = OFF` restores V1.5-style audible behavior:
  continuous pinch amp remains active, while the articulation envelope is
  bypassed.
- The new OSC address is isolated:
  `/sample/left/articulation/gate`.
- Future mappings may ignore, replace, or remove this event without changing
  right-hand pitch or left-hand tone control.

## Current checkpoint (2026-10-19)

V2a articulation/filter envelopes and V2a.1 runtime calibration are implemented
on top of V1.5 tone control. Both envelope toggles default to OFF; enable them
in the subtractive probe to audition V2a.

The hands player sends `/sample/panic` on normal exit, Ctrl+C, or camera errors.
Both SC probes release amp to zero on panic; the subtractive probe also closes
articulation gate. After receiving a left-pinch packet, each probe watches for
one second without another pinch packet and releases input locally. The check
runs every 0.1 seconds; configured amp release and FX tails still apply.
Input resumes with the next pinch packet, preserving the manual performance gate.
Python also repeats articulation OFF after hand-loss timeout to tolerate UDP loss.

The separate sounddevice player in `gui/theremin_gui.py` now uses MediaPipe Tasks
and the bundled model. It remains separate from the OSC/SC mapping UI.

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
& 'C:\Program Files\SuperCollider-3.14.1\sclang.exe' -D (Join-Path $PWD 'tests\sc_input_lifecycle.scd')
```

Automated checks cover Python logic and shutdown, bundled model initialization,
generated player landmark processing, full SC compilation, SynthDef generation,
and receiver timeout/resume/panic behavior without camera or audio hardware.
Remaining manual checks: calibrate pinch during performance, listen to envelope
and release behavior, quit/disconnect/force-stop while playing, and switch probes.
Low-latency mode and Ableton integration remain unimplemented.

## Setup

Windows PowerShell setup:

```powershell
git clone https://github.com/aoba-aoband/handtrack_music_platform.git
cd handtrack_music_platform
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks virtual environment activation, allow locally created
scripts for the current user and then activate the environment again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## SuperCollider Setup

1. Start SuperCollider.
2. Choose one probe: `sc/basic_receiver.scd` for the existing additive / FX
   probe, or `sc/subtractive_probe.scd` for the separate subtractive-synthesis
   probe.
3. Evaluate the block in that file.
4. The receiver listens for OSC on `127.0.0.1:57120`.
5. That host and port should match the SuperCollider target in `config.py`.

## Run Prototype

Main practice prototype command:

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel
```

Start with pitch quantization enabled:

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel --quantize-pitch
```

Measure current frame timing before making low-latency behavior changes:

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel --show-performance-stats
```

`--show-performance-stats` prints periodic console summaries for capture,
MediaPipe inference, feature extraction, mapping, OSC send time, drawing,
display/wait time, total frame time, and effective FPS. It is measurement only:
it does not enable a low-latency mode, skip drawing, drop frames, change OSC
addresses, or otherwise change the hand-tracking behavior.

## Basic Operation

- Press `q` in the preview window to quit.
- Move the right hand up and down to control the pitch candidate.
- Move the middle finger above the index finger to trigger the sample octave
  shift candidate.
- Use left-hand pinch for the amp candidate.
- Use the settings panel to change:
  - Pitch Min note
  - Pitch Max note
  - Root
  - Scale
  - Quantize
  - Guide Mode

## Known Prototype Limitations

- The UI is an OpenCV trackbar panel, so it is visually temporary.
- Root and Scale are numeric trackbars, not an intuitive final UI.
- MediaPipe handedness and hand index are not yet a complete stable role
  tracking system.
- Tracking dropout can still make the sound jump unnaturally.
- The SuperCollider sound, `Lag`, and amp behavior are still probe-level
  designs.
- Ableton / Max for Live integration is not yet fully implemented.

## Current Status

- Git tracking is initialized.
- Python can send OSC to SuperCollider.
- OpenCV can display a webcam preview and quit with `q`.
- MediaPipe Hands can draw hand landmarks on the camera preview.
- Hand landmarks can be converted into neutral `HandFeatures`.
- `HandFeatures` can be mapped to generic `ControlEvent` addresses such as:
  - `/hand/0/index/x`
  - `/hand/0/index/y`
  - `/hand/0/middle/x`
  - `/hand/0/middle/y`
  - `/hand/0/thumb/x`
  - `/hand/0/thumb/y`
  - `/hand/0/pinch`
- `python main.py hands --send-osc` can send generated hand `ControlEvent`
  values to SuperCollider.
- Python generates sample pitch events including `/sample/right/pitch/norm`,
  `/sample/right/pitch/freq`, `/sample/right/pitch/octave_shift`, and
  `/sample/right/pitch/freq_with_octave`.
- The sample middle-finger octave gesture is minimally implemented: when
  `middle_tip_y < index_tip_y`, `octave_shift` becomes `1.0` and
  `freq_with_octave` becomes the base pitch frequency doubled.
- Python also emits `/sample/right/pitch/final_freq`. Without
  `--quantize-pitch`, `final_freq` matches `freq_with_octave`; with
  `--quantize-pitch`, it uses `quantized_freq`.
- The SuperCollider probe uses `/sample/right/pitch/final_freq` directly for
  the confirmation Synth's pitch, so `--quantize-pitch` can switch the audible
  probe between continuous and scale-snapped pitch.
- The SuperCollider probe now includes a small synth control UI for response
  and tone-shaping parameters such as lag, portamento, soft clipping, output
  level, filter shaping, and the left-hand pinch amp range.
- The SuperCollider probe also has a performance gate. With the Probe Synth
  Controls window focused, pressing the spacebar toggles a crescendo /
  decrescendo-style master gate.
- The SuperCollider probe opens a small sound-design monitor panel. It shows
  target/followed frequency, target/followed amp, gate envelope, output level,
  softClip, and filter state, with buttons for waveform and frequency scopes.
- The SuperCollider probe also opens a conceptual visualizer for sound design:
  LPF/filter shape, soft clip curve, and pitch-follow / portamento history.
- The SuperCollider probe now includes organ-style additive synthesis, a
  filtered delay, and a reverb stage for tone-design experiments.
- A minimal sample pitch guide-line overlay is available in the camera preview.
  It supports `simple`, `chromatic`, and `scale` display modes from the same
  Python pitch range settings used by the sample mapper.
- Scale guide display can use a root note and scale to show only matching
  guide notes. Pitch quantization is now minimally implemented for the sample
  probe via `--quantize-pitch`.

## Run Commands

OSC connectivity smoke test:

```powershell
python main.py
```

Raw camera smoke test:

```powershell
python main.py camera
```

MediaPipe Hands landmark preview:

```powershell
python main.py hands
```

Show neutral feature values on the preview:

```powershell
python main.py hands --show-features
```

Show generated generic `ControlEvent` values on the preview:

```powershell
python main.py hands --show-events
```

Send generated hand `ControlEvent` values over OSC:

```powershell
python main.py hands --show-events --send-osc
```

Try the handedness-based sample musical mapping with continuous pitch:

```powershell
python main.py hands --show-events --sample-mapping --send-osc
```

Try the sample mapping with quantized pitch:

```powershell
python main.py hands --show-events --sample-mapping --send-osc --quantize-pitch --pitch-root A --pitch-scale minor-pentatonic
```

Try quantized pitch with matching scale guide lines:

```powershell
python main.py hands --show-events --sample-mapping --send-osc --quantize-pitch --pitch-root A --pitch-scale minor-pentatonic --show-pitch-guides --pitch-guide-mode scale --pitch-guide-root A --pitch-guide-scale minor-pentatonic
```

Show simple sample pitch guide lines on the preview:

```powershell
python main.py hands --sample-mapping --show-pitch-guides
```

Show chromatic guide lines and emphasize the root pitch class:

```powershell
python main.py hands --sample-mapping --show-pitch-guides --pitch-guide-mode chromatic --pitch-guide-root A
```

Show A minor pentatonic guide lines:

```powershell
python main.py hands --sample-mapping --show-pitch-guides --pitch-guide-mode scale --pitch-guide-root A --pitch-guide-scale minor-pentatonic
```

Show C major guide lines:

```powershell
python main.py hands --sample-mapping --show-pitch-guides --pitch-guide-mode scale --pitch-guide-root C --pitch-guide-scale major
```

Show sample pitch events and guide lines together:

```powershell
python main.py hands --show-events --sample-mapping --show-pitch-guides
```

Override the sample pitch range at startup:

```powershell
python main.py hands --sample-mapping --show-pitch-guides --pitch-min 110 --pitch-max 440
```

The `--pitch-min` and `--pitch-max` options also update the guide-line Hz
labels.

Use another camera:

```powershell
python main.py hands --camera-index 1
```

Show periodic performance stats while running the normal sample mapping patch:

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel --show-performance-stats
```

The reporting interval can be changed with `--performance-stats-interval`,
for example `--performance-stats-interval 2.0`.

## Performance Log Visualization

Performance stats can be saved to a log file and converted into CSV and charts
with `tools/plot_perf_log.py`. This is useful for comparing the current
pipeline before and after future low-latency work.

Record a performance log:

```powershell
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel --show-performance-stats *>&1 | Tee-Object -FilePath "logs\perf_$ts.txt"
```

Plot a specific log:

```powershell
python .\tools\plot_perf_log.py .\logs\perf_YYYYMMDD_HHMMSS.txt --out-dir .\analysis\perf_YYYYMMDD_HHMMSS
```

Generated outputs:

- `perf_summary.csv`
- `total_frame_time.png`
- `fps_over_time.png`
- `stage_timings_over_time.png`
- `average_stage_breakdown.png`
- `max_stage_breakdown.png`
- `hands_vs_mediapipe.png`

Suggested reading order:

- `average_stage_breakdown.png`
- `stage_timings_over_time.png`
- `total_frame_time.png`
- `fps_over_time.png`
- `hands_vs_mediapipe.png`

`logs/` and `analysis/` are generated-output directories ignored by Git. Do
not commit performance logs, CSV files, or generated charts.

## SuperCollider Probe

Evaluate `sc/basic_receiver.scd` in SuperCollider before running a Python OSC
test. The receiver listens on `127.0.0.1:57120`, matching `config.py`.

The current SuperCollider receiver treats `/hand/...` as neutral
`ControlEvent` data for inspection. The `/hand/0/...` handlers can post
received values to the SuperCollider Post window when debugging is enabled, but
they do not control the probe Synth's `freq` or `amp`.

Per-event Post window logging is off by default so sound checks stay readable.
Set `~debugHandEvents = true` for `/hand/...` logs or
`~debugSampleEvents = true` for sample `freq` / `amp` logs.

The temporary probe Synth is controlled only by the sample musical mapping
events:

- `/sample/right/pitch/final_freq` to `freq`
- `/sample/left/pinch` to `amp`

`/sample/right/pitch/freq` is still received as a base-pitch value for
inspection. `/sample/right/pitch/octave_shift`,
`/sample/right/pitch/freq_with_octave`, and
`/sample/right/pitch/quantized_freq` can be posted for debugging.
SuperCollider does not calculate octave shifts, scale, key, or quantization;
it uses the final frequency candidate sent by Python.

`sc/basic_receiver.scd` also opens a prototype synth control UI. It is still a
probe interface, not a finished instrument panel, but it lets the
SuperCollider side adjust how the received `final_freq` is followed and
sounded. Current controls include:

- `freqLag`
- `ampLag`
- Performance Gate, also toggleable with the spacebar when the Probe Synth
  Controls window has focus.
- `crescendoTime` / `decrescendoTime`
- `portamentoOn` / `portamentoTime`
- `softClipOn` / `softClipDrive` / `softClipMix`
- `filterOn` / `filterCutoff` / `filterRq` / `filterMix` / `filterLag`
- `outputLevel`
- `ampMin` / `ampMax`

A separate `Probe Synth Monitor` window is also opened as a sound-design aid,
not a finished UI. It shows `targetFreq`, `followedFreq`, `targetAmp`,
`followedAmp`, the performance gate and gate envelope, `outputLevel`, current
soft clipping values, current filter values, and the lagged `filterFreq` used
inside the Synth.

The monitor includes `Open Scope`, which calls `s.scope(2)` for the final
2-channel output waveform, and `Open FreqScope`, which opens SuperCollider's
standard frequency display. These are meant to make soft clipping and filter
changes easier to judge while shaping the probe synth.

A separate `Probe Synth Visualizer` window shows three conceptual diagrams for
sound design. The LPF visual places `filterCutoff` on a log-like frequency
axis and now uses an RLPF-like approximation instead of the older hard-cut
concept curve. It is still not a measured spectrum analyzer or an exact copy
of SuperCollider's internal `RLPF.ar`, but it better shows that low
`filterRq` values can become sharper and more resonant around the cutoff.
The LPF / Filter visual uses a dB scale from `+12 dB` to `-36 dB`, with a
clear `0 dB` reference line and dB tick marks, so resonance peaks and
high-frequency rolloff are easier to read without flattening the curve at the
top of the display.
For simple high-frequency smoothing, mid-to-high `filterRq` values such as
`0.5` to `1.0` are usually easier to handle. The Soft Clip visual shows the
dry line and the `tanh`-style curve created by `softClipDrive` and blended by
`softClipMix`. The Pitch Follow visual keeps a short history of `targetFreq`
and `followedFreq` so lag and portamento delay can be seen while playing.
These drawings are intentionally approximate concept diagrams, not accurate
measurement instruments.

The LPF visual also includes frequency guide marks so it is easier to see
whether the cutoff is in the low, mid, or high range. The visualizer includes
a simple harmonic bar display for the additive source and a conceptual delay
display for delay time and feedback.

A separate `Probe Synth Additive / FX Controls` window exposes additional
probe-level sound design controls. The additive source is an organ-style
12-harmonic oscillator: each harmonic can be controlled independently, the
harmonic sum is normalized, and the result is blended with the base sine
source before soft clipping and the main filter. A filtered delay is placed
after the main filter, and reverb is placed after the delay. These are still
probe synth tone-shaping tools, not a finished instrument or effects spec.

The design boundary stays the same: Python decides pitch, scale,
quantization, octave candidates, and `final_freq`. SuperCollider receives that
`final_freq` and handles response feel, portamento, soft clipping, filter
shaping, output level, performance gating, and the local amp range used for
the sample probe.
The gate starts off by default so the probe can be brought in intentionally;
the Gate button and spacebar perform the same toggle. `crescendoTime` and
`decrescendoTime` control the fade-in and fade-out time. This is a probe synth
performance helper, not a finished instrument specification.

The filter section is placed after soft clipping and before `outputLevel` and
the performance gate:

```text
SinOsc -> ampLag -> soft clipping -> filter -> outputLevel -> performanceGate -> Out
```

The current filter uses `RLPF.ar` to tame high-frequency content created by
soft clipping. `filterCutoff`, `filterRq`, `filterMix`, and `filterLag` are
adjustable from the SuperCollider UI. This is a probe synth tone-shaping tool,
not a finished sound design.

### Subtractive Synthesis Probe (V1)

`sc/subtractive_probe.scd` is a separate, educational and playable
subtractive-synthesis probe. It is not an extension of `basic_receiver.scd`:
the basic receiver remains the additive / soft-clip / delay / reverb probe,
while the subtractive probe keeps the core `source -> filter -> amp -> output`
structure easy to hear and inspect.

To use it, evaluate `sc/subtractive_probe.scd` in SuperCollider, then run the
existing Python command unchanged:

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel
```

It uses the existing sample mapping only:

- `/sample/right/pitch/final_freq` updates `freq`.
- `/sample/left/pinch` is mapped from `0..1` into `ampMin..ampMax` and updates
  `amp`.

Its signal path is:

```text
oscillators / sub / noise
-> source mix
-> RLPF
-> amp response
-> performance gate
-> LeakDC / Limiter
-> Out
```

The V1 controls cover oscillator 1 and a switchable oscillator 2 (Saw, Pulse,
or Triangle), octave, detune, oscillator mix, manual pulse width, sub mix, and
noise mix. The filter section provides cutoff, `filterRq`, dry/filter mix,
filter lag, and key tracking. `keyTracking = 0` leaves cutoff fixed; higher
values raise the effective cutoff for higher pitches so their relative
brightness is easier to retain. Response controls provide `freqLag`, separate
`ampAttack` / `ampRelease`, `outputLevel`, and the pinch amp range.

The `Subtractive Probe Controls` window has a Gate button; with that window
focused, the spacebar performs the same performance-gate toggle. Its monitor
shows target/followed frequency and amp, gate envelope, effective cutoff,
filter state, oscillator waveforms, and output level, with Scope and FreqScope
buttons for final-output inspection. `Reset defaults` updates the GUI and the
running Synth together.

Evaluate one probe at a time. Both probe files use a small shared cleanup hook:
evaluating either file frees the other probe's Synth, its sample-mapping
OSCdefs, and its control/monitor windows, so the same OSC messages do not make
both probes sound. Re-evaluating either individual probe also replaces its old
Synth, OSCdefs, and windows.

V1 intentionally did not add LFOs, PWM, filter envelopes, ADSR or note
triggers, unison, alternate filter types, delay/reverb, a custom visualizer,
or new Python gestures / OSC addresses. V2a below adds only the isolated
sample-mapping articulation gate and filter envelope experiment.

### V1.5: Left-Hand Tone Control

V1.5 adds one sample-mapping event without changing the existing Python launch
command:

```powershell
python main.py hands --sample-mapping --send-osc --show-pitch-guides --show-settings-panel
```

`/sample/left/tone/norm` carries the left index-tip X position as an unchanged
`0..1` tone candidate. Python does not invert it, convert it to Hz, or smooth
it. `sc/subtractive_probe.scd` interprets it as cutoff control; the existing
`sc/basic_receiver.scd` deliberately does not use this new event.

With `handToneOn` OFF, the V1 `Manual cutoff` (`filterCutoff`) remains the
selected base cutoff. With it ON, SuperCollider optionally inverts the tone
norm with `toneInvert`, maps it exponentially into the
`toneMinCutoff..toneMaxCutoff` range, and uses the resulting
`handToneCutoff` as the base cutoff. The selected base cutoff is then adjusted
by `keyTracking` and smoothed by `filterLag` before reaching `RLPF`.

`toneMinCutoff` and `toneMaxCutoff` define the dark-to-bright playing range;
the UI keeps their order valid. `toneInvert` reverses which left-hand direction
means darker or brighter. The subtractive monitor shows the mode, raw target
tone norm, mapped hand-tone cutoff, manual cutoff, and effective cutoff.

### V2a: Articulation Gate + Filter Envelope

V2a adds one sample-mapping OSC event:

```text
/sample/left/articulation/gate
```

Python derives this event from left-hand pinch using threshold + hysteresis.
The default thresholds are `articulation_gate_on_threshold = 0.65` and
`articulation_gate_off_threshold = 0.45`; left-hand tracking loss releases the
gate after `articulation_hand_loss_release_seconds = 0.25`. Python does not
shape envelopes, choose ADSR timings, or convert this gate into filter cutoff.
It only sends `0` or `1`, while preserving `/sample/left/pinch`,
`/sample/left/tone/norm`, and `/sample/right/pitch/final_freq`.

#### V2a.1: Runtime Mapping Calibration

With `--show-settings-panel`, OpenCV now opens a separate `Mapping Settings`
window in addition to the existing `Pitch Settings` window. It provides:

- Articulation threshold
- Hysteresis width
- Hand-loss release time in milliseconds

The calibration uses:

```text
gateOn  = threshold
gateOff = max(0, threshold - hysteresis width)
```

A pinch at or above `gateOn` opens the gate, a pinch at or below `gateOff`
closes it, and values between them retain the previous gate state. The camera
preview shows `Articulation Mapping` with the current raw left-pinch value,
gate state, effective on/off thresholds, and loss-release time.

Pinch values vary with camera distance, hand size, and how the hand opens, so
the defaults are starting points rather than universal correct thresholds.
Watch the live monitor at a natural playing distance and calibrate from the
values you actually reach. GUI changes take effect immediately but only for
the current session; `config.py` remains the startup-default source and is not
rewritten.

A future Mapping GUI may make the articulation source selectable from left
pinch, right pinch, left-hand proximity candidate, right-hand proximity
candidate, or off. A proximity candidate would be a separately evaluated
performance feature, not a claim of physical-distance measurement from a
monocular webcam. V2a.1 keeps the source fixed to left pinch and adds no stereo
vision or depth-camera dependency.

SuperCollider receives `/sample/left/articulation/gate` and uses it for:

- articulation amp envelope
- filter envelope
- envelope timing and cutoff multiplier

`articulationOn` defaults to OFF. When it is OFF, V1.5-style continuous pinch
amp remains active and the articulation envelope is bypassed, so incoming gate
events do not force the sound closed. When `articulationOn` is ON,
`articulationGate` opens with `articulationAttack` and releases with
`articulationRelease`. This is separate from `ampAttack` / `ampRelease`:

- `ampAttack` / `ampRelease`: response time for continuous pinch amp
- `articulationAttack` / `articulationRelease`: onset and release shape made
  from the threshold gate

`filterEnvOn` defaults to OFF. When it is OFF, no filter-envelope multiplier is
added to the base cutoff. The filter envelope is active only when both
`filterEnvOn` and `articulationOn` are ON. `filterEnvAmountOctaves` is an
octave multiplier amount, not a Hz offset: larger values open the cutoff more
at articulation onset.

V2a signal path:

```text
oscillators / sub / noise
-> source mix
-> RLPF
-> followed pinch amp
-> articulation amp envelope
-> performance gate
-> LeakDC / Limiter
-> Out
```

Filter cutoff path:

```text
manual cutoff or hand-tone cutoff
-> key tracking
-> filter lag
-> optional filter envelope
-> RLPF cutoff
```

Still intentionally unimplemented:

- LFO
- PWM
- pinch-independent articulation gesture
- explicit trigger event
- alternate filter types
- unison
- polyphony

This sample uses MediaPipe `handedness`, but it is still an example patch, not
a platform rule. The sample mapping debounces handedness labels for a few
frames so a single-frame Left/Right misclassification is less likely to swap
the sample pitch and amplitude roles.

This project is a platform for converting hand landmark information into music
control streams, not a single fixed theremin design. Future musical mappings
should be treated as configurable patches or examples.

Future debug TODO: the Python side can generate neutral events for multiple
hands, including `/hand/1/index/x`, `/hand/1/index/y`, `/hand/1/thumb/x`,
`/hand/1/thumb/y`, and `/hand/1/pinch`. The current
`sc/basic_receiver.scd` probe only posts the `/hand/0/...` neutral events.
When debugging two-hand behavior, either add matching Post display handlers for
`/hand/1/...` or consider a generic OSC logger for the `/hand/...` event family.

### Smoothing and Portamento Notes

The current `basicOscProbe` Synth in `sc/basic_receiver.scd` exposes
`freqLag`, `ampLag`, `portamentoOn`, and `portamentoTime` in the
SuperCollider probe UI. The defaults are still temporary connection-probe
values, not a fixed instrument specification. Depending on the piece, ensemble
context, and playing style, the best feel may be fast tracking, deliberately
delayed smooth motion, or something in between.

It is useful to separate two related ideas:

- Smoothing reduces MediaPipe-derived jitter and tiny control-value wobble.
- Portamento defines the musical movement between pitch targets.

The current probe separates the basic controls: `freqLag` is used when
portamento is off, `portamentoTime` is used when portamento is on, and
`ampLag` follows amplitude independently. This is still a probe-level design,
but the values are now adjustable from SuperCollider instead of being only
hard-coded in the SynthDef. Future control surfaces could also include an
OpenCV overlay, MIDI CC, OSC settings messages, config values, or CLI startup
options.

Future settings candidates:

- `freq_smoothing_time`
- `amp_smoothing_time`
- `portamento_time`
- `portamento_mode`
- `quantized_pitch_glide`
- `snap_strength`
- Hysteresis / deadband.

Implementation direction: Python should decide pitch, scale, quantization, and
`final_freq`. SuperCollider should decide how the Synth follows and sounds that
received `final_freq`. Those follow/response values should eventually be
changeable at runtime, for example as Synth arguments or OSC settings, rather
than being permanently embedded as fixed `SynthDef` constants.

## Coordinate Notes

- `/hand/0` means the first hand reported by MediaPipe in the current frame.
  It is not guaranteed to be the right hand or the left hand.
- MediaPipe also reports `handedness` labels such as `Left` and `Right`.
  These are currently displayed for inspection with `--show-features` or
  `--show-events`, but they are not yet used for fixed right-hand or left-hand
  musical routing.
- MediaPipe image coordinates are normalized. `x` and `y` are roughly `0..1`.
- Image `y` is top-to-bottom: the top of the image is `0`, and the bottom is
  `1`. Raising a hand generally makes `index_tip_y` smaller.
- The camera preview in `hands` mode is mirrored for easier interaction, but
  the extracted feature values remain based on the original detection frame.
  Handedness can be confusing when comparing camera input, mirrored display,
  and user perspective, so it should be verified before using it for a musical
  mapping.

## Hand Index, Handedness, and Roles

`/hand/0` and `/hand/1` are detection indexes, not stable right-hand or
left-hand identities. `/hand/0` is the first hand returned by MediaPipe for the
current frame, numbered by the Python feature/event layer. If a patch uses
`/hand/0` directly for pitch and `/hand/1` directly for amplitude, those roles
can wobble when MediaPipe changes detection order, loses a hand, or redetects
hands.

The `/sample/right/...` and `/sample/left/...` event streams are different:
they are sample-only musical events built from MediaPipe `handedness` labels.
The current `--sample-mapping` mode aims for Right-hand and Left-hand sample
roles, but its stabilization is only a debounce per `hand_index`. That helps
with brief handedness label flicker, but it is not a complete solution when
the order of `hand 0` and `hand 1` itself swaps.

For a more instrument-like mapping, add a role/identity layer before assigning
musical meaning. Possible future names include `stable_right_hand`,
`stable_left_hand`, `role_id`, or a hand identity tracker. That layer should
own the question "which physical hand has this musical role?" instead of
putting that responsibility on `/hand/0` or `/hand/1`.

## Design Boundary

The Python side currently produces neutral control data:

```text
MediaPipe Hands -> HandFeatures -> ControlEvent -> output adapter
```

Musical interpretation belongs after this boundary. For example, right-hand Y
to pitch or left-hand pinch to amplitude should be implemented as a patch,
configuration, or example mapping, not as a fixed platform rule.

## Future Pitch Mapping Notes

The current sample mapper keeps `/sample/right/index/y_inverted` as a
normalized `0..1` value and also emits `/sample/right/pitch/norm`,
`/sample/right/pitch/freq`, `/sample/right/pitch/octave_shift`, and
`/sample/right/pitch/freq_with_octave`. For now, Python maps pitch norm to a
base frequency with a configurable exponential range, then applies the sample
middle-finger octave gesture to produce `freq_with_octave`. This is a working
sample mapping, not a final pitch design.

The current order is roughly:

```text
pitch norm -> base freq -> octave shift -> freq_with_octave
```

When scale, key, and quantization are introduced, this order should be
revisited. Possible future orders include:

- `norm -> scale/key quantization -> octave shift -> final freq`
- `norm -> octave shift -> quantization -> final freq`

The camera guide-line overlay now has `simple`, `chromatic`, and `scale`
display modes. `simple` draws evenly spaced horizontal lines for
`pitch_norm = 0.0, 0.25, 0.5, 0.75, 1.0`. `chromatic` draws semitone guide
lines across the active pitch range and emphasizes the configured root pitch
class. `scale` draws only the semitone guide lines that belong to the selected
root and scale. These guide modes are visual only; they do not quantize
`/sample/right/pitch/freq` or `/sample/right/pitch/freq_with_octave`.
`--quantize-pitch` switches `/sample/right/pitch/final_freq` from continuous
`freq_with_octave` to scale-snapped `quantized_freq`, and the current
SuperCollider probe plays `final_freq`.

For a fuller instrument design, keeping key, scale, range, quantization, and
normalized-to-pitch conversion in Python should let the camera preview guide
lines and the emitted `pitch`, `freq`, or `midi` values share the same logic.
If SuperCollider owns its own separate `0..1 -> freq` conversion, Python
guide-line calculation and SC pitch conversion can drift over time.

Normalized pitch-like values are still useful, but final musical pitch mapping
is a candidate for `mapping.py` or a future `src/music/` layer rather than
`features.py`. Current and possible future event names include:

- `/sample/right/pitch/norm`
- `/sample/right/pitch/freq`
- `/sample/right/pitch/octave_shift`
- `/sample/right/pitch/freq_with_octave`
- `/sample/right/pitch/midi`
- `/sample/right/pitch/degree`
- `/sample/right/pitch/quantized`

Possible future structure:

- `features.py` keeps only neutral hand-derived features.
- `src/pitch.py` keeps shared pitch helpers such as note names, pitch classes,
  scale definitions, frequency/MIDI conversion, and guide-line generation.
- `mapping.py` or `src/music/` handles key, scale, range, quantization, and
  pitch conversion.
- Camera guide-line drawing reads the same pitch mapping logic and uses the
  same final pitch information that the sound output uses.
- SuperCollider focuses on synthesis from received `freq` values or
  MIDI-derived values.

## Future Scale / Key / Quantization Notes

Before adding scale, key, or quantization, the pitch terms should stay clear:

- `pitch_norm`: a continuous `0.0..1.0` pitch candidate derived from neutral
  hand data such as right-hand `index_tip_y`.
- `pitch/freq`: a continuous base frequency converted from `pitch_norm`.
- `octave_shift`: an octave-change candidate from a sample gesture such as
  the middle finger moving above the index finger.
- `freq_with_octave`: the continuous frequency candidate after applying
  `octave_shift` to the base frequency.
- `final_freq`: the current frequency value used by the SuperCollider probe;
  continuous unless `--quantize-pitch` selects `quantized_freq`.
- Quantized pitch: a pitch candidate after snapping or rounding to a selected
  scale and key.

The order for scale, key, and quantization is still undecided. Candidate
orders include:

- A: `pitch_norm -> scale/key quantization -> octave shift -> final freq`
- B: `pitch_norm -> octave shift -> scale/key quantization -> final freq`
- C: `pitch_norm -> continuous freq` and `pitch_norm -> quantized freq`, with
  both streams emitted for comparison or patch choice.

A likely important direction is that Python should be the single source of
truth for sample pitch mapping. The guide-line overlay and OSC output should
read the same pitch mapping logic. If SuperCollider has a separate scale/key
conversion, the preview guide lines and the audible pitch can drift apart.

The current guide-line code can already display root and scale information,
and Python can emit and play quantized pitch candidates through `final_freq`.
The next pitch-design steps include unifying guide settings with quantization
settings, tuning snap strength, adding hysteresis, deciding how portamento
should behave around snapped notes, and designing a scale/key UI.

Possible future pitch events:

- `/sample/right/pitch/midi`
- `/sample/right/pitch/degree`
- `/sample/right/pitch/quantized_norm`
- `/sample/right/pitch/quantized_freq`
- `/sample/right/pitch/final_freq`

The current guide lines can be evenly spaced, chromatic, or scale-filtered.
They can already match the notes that the quantizer can choose when the same
root and scale are used. The remaining design work is making that relationship
ergonomic and explicit so the active pitch range, key, scale, octave-shift
behavior, guide display, and final emitted pitch value stay aligned.

## Future Settings UI Notes

The current sample pitch range can be changed without editing `mapping.py`.
`config.py` defines `SAMPLE_MAPPING` values such as `pitch_min_freq` and
`pitch_max_freq`, and the hands smoke test can override them at startup with
CLI arguments:

```powershell
python main.py hands --show-events --sample-mapping --send-osc --pitch-min 110 --pitch-max 440
```

The camera guide display can also be adjusted from the CLI with
`--pitch-guide-mode`, `--pitch-guide-root`, and `--pitch-guide-scale`.

This is an intermediate step toward a more playable settings workflow. In the
future, performance-facing settings should be adjustable without direct code
edits. The exact UI shape is still open. Possible directions include:

- Simple controls overlaid on the OpenCV preview.
- A separate settings panel window.
- A Web UI.
- MIDI controller or MIDI CC control.
- Hot reloading from a settings file.

Settings that may eventually belong in that layer include:

- Pitch range.
- Pitch guide mode.
- Root note.
- Scale.
- Quantization on/off.
- Smoothing amount.
- Portamento time / mode.
- Quantized pitch glide.
- Snap strength.
- Hysteresis / deadband.
- Gesture mappings.
- Amp range.

This is only a planning note for now. The current implementation should remain
focused on configurable sample mapping, not a fixed theremin design or a final
settings UI.

## Future Gesture Mapping Notes

The middle-finger octave gesture is now minimally implemented as a sample
mapping. When the middle finger moves higher than the index finger, Python
emits an octave candidate. MediaPipe image coordinates use `y = 0` at the top
of the image and `y = 1` at the bottom, so the current raw condition is
`middle_tip_y < index_tip_y`.

`features.py` now exposes neutral middle-finger features, `middle_tip_x` and
`middle_tip_y`. Those values remain landmark-derived features, not fixed
musical roles.

Current sample events include:

- `/sample/right/pitch/octave_shift`
- `/sample/right/pitch/freq_with_octave`

`octave_shift` is `1.0` when `middle_tip_y < index_tip_y`, otherwise `0.0`.
`freq_with_octave` currently doubles the base `/sample/right/pitch/freq` when
`octave_shift` is active. The SuperCollider probe now uses
`/sample/right/pitch/final_freq` for the confirmation Synth's pitch, so the
same octave behavior is audible when `final_freq` is continuous.

This is not a fixed platform rule. It should still be treated as a sample
musical mapping candidate. Future refinements include false-trigger
protection, hysteresis, a gesture threshold or margin, smoothing/debounce, and
integration with scale, key, quantization, and guide-line logic.

Any octave gesture design should stay compatible with future scale, key,
quantization, and camera guide-line logic.

## Future Amp Mapping Notes

The current `sc/basic_receiver.scd` probe maps `/sample/left/pinch` to `amp`
with `value.linlin(0, 1, 0.02, 0.25)`. Because the minimum amp is `0.02`,
`pinch = 0` does not become complete silence. That is useful for connection
checking because the synth remains audible, but it is not a fixed volume
control specification.

For a fuller instrument design, revisit what left-hand pinch should mean.
Possible directions:

- Mute completely near `pinch = 0`.
- Add a `gate` or ASR envelope instead of treating pinch as raw continuous amp.
- Use a dB or exponential loudness curve instead of a linear `amp` curve.
- Tune the maximum amp separately from the gesture range.
- Give `freq` and `amp` separate lag times.
- Keep open the possibility that pinch controls filter cutoff, reverb send,
  delay send, or another expressive parameter instead of volume.

## Future Tracking Dropout Notes

When the hand moves quickly, MediaPipe can briefly lose tracking. On
reacquisition, landmark coordinates may jump far from the previous values,
which can look like a control-value warp. That jump can create unnatural
texture in the SuperCollider sound. This is not a connection-check failure; it
is a tracking dropout / reacquisition issue to handle during the instrument
design phase.

Possible future responses:

- Hold the last value while a hand is briefly lost.
- Close `gate` or `amp` after the hand has been lost for a short timeout.
- Fade in after reacquisition.
- Ignore coordinate jumps that are too large as outliers.
- Consider a slew limiter or One Euro Filter.
- Decide whether to accept control values based on tracking confidence or
  presence confidence.
