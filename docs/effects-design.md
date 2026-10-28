# Audio / Effects integration design and verification

This describes the Regular UI path. The independent sounddevice player and
legacy OSC 57120 CLI are not integrated into it. No additional SC plugins are
required. See [Quick Start](../QUICKSTART.md) / [日本語](../QUICKSTART_ja.md).

## Routing and ownership

```text
MediaPipe → existing pitch/octave/quantizer → source oscillator (+ SC Vibrato)
         → original probe processing/gates → private stereo instrument bus
         → reorderable Tremolo / Distortion / Fuzz / Delay / Reverb → master
SoundIn 1/2 → stereo Thru (On, Level) ──────────────────────────────→ master
master → DC removal → hard peak cap ±0.98 → immediate PANIC mute → output 1/2
```

Basic's original delay/reverb are compile-time excluded in Regular mode. Legacy
mode retains them. Both probes retain their original parameter catalogs (46/41,
including readouts); common Delay/Reverb inherit the original ranges, steps,
units and defaults. UI module registration is separate from parameter contracts.

SC owns device enumeration and applies options before boot. Python owns machine
profiles, Patch/Layout and process lifetime. Owned audio reconfiguration replaces
the entire owned sclang/scsynth tree, resets the return socket/session ID, and
increments a process epoch. SC routines, monitor-bus readings, node callbacks and
delayed resource frees carry generation tokens. Old callbacks cannot populate
the new graph. Windows uses an owned Job Object; POSIX uses an owned process
group. External SC languages are never killed; reconfiguration there requests
only their server reboot. Failures remain muted and require explicit reapply.

The actual graph has one source, five serial FX nodes and a master, plus a Thru
node only when stereo input exists. Probe switching uses the existing cleanup
hook and preserves common FX values. Reorder creates a parallel chain, crossfades
for 20 ms, then frees the old chain after 160 ms (buses/buffers after a guard
interval). Tail history is reset on reorder. Normal Delay/Reverb OFF fades new
input over 30 ms but allows accumulated tails. PANIC gates the final output
immediately and clears the active FX history. SC UI-contact timeout is 2 s;
angle packets stale for 0.6 s return the amount toward zero using native lags.

### Local SC native teardown finding

During verification on this Windows SC 3.14.1 installation, minimal examples
using several RT-memory UGens (including DelayC/LocalIn/SendReply/Limiter) produced
native access-violation exits on teardown. A definitive upstream cause has not
been established. This is a local observation, not a claim that all SC builds
have this defect. The Regular path uses explicit buffer-backed delay, control-bus
monitor polling, and a peak cap instead of the old Subtractive lookahead limiter.
Consequently its output protection can sound different on excessive peaks; it
has no limiter lookahead. Legacy probe DSP keeps its old limiter/FX behavior.

All production offline test scenes include node and buffer frees. The owned
process restart also handles a locally observed native server quit hang without
touching external sessions. A restricted-process verification attempt later
failed once while recreating a probe; the full unrestricted rerun passed. Native
failure cannot be excluded in every installation. A connected external session
whose server cannot quit requires manual server termination; retry is bounded,
not an automatic restart loop. Native Scope/FreqScope teardown also depends on
the installed SC build. Inspect the SC log on any failure.

## Audio device policy and sources

The [official audio-device guide](https://doc.sccode.org/Reference/AudioDeviceSelection.html)
documents pre-boot device listing, restarting after selection, macOS rate
matching/aggregate devices and Windows API selection. The
[ServerOptions reference](https://doc.sccode.org/Classes/ServerOptions.html)
defines inDevices/outDevices, input/output selection and sample-rate options.
The UI preserves SC's complete API-prefixed device names. System default remains
an explicit user choice; unavailable named choices never silently fall back.

For macOS separate input/output, this app chooses sampleRate nil and advises
matching rates in Audio MIDI Setup, then checking logs or an Aggregate Device on
failure. The [community discussion](https://scsynth.org/t/booting-sc-reliably-with-different-in-and-out-devices/12878)
contains anecdotal reports about separate devices and removing an explicit rate.
It is not a specification or evidence that iPad/UR44C will reliably boot. That
pair and macOS are untested here. Windows does not inherit this macOS override.

## Modulation and mappings

Vibrato multiplies the already followed/quantized oscillator frequency by
`2 ** (LFO * depthCents / 1200)`, including Osc 2/Sub and additive harmonics.
Tremolo gain is `1 - depth * (LFO + 1) / 2`, so depth 0.6 ranges from 0.4 to 1.
The LFOs run in SC, independently of camera FPS. Sine/Triangle/Square are native
UGens; a 3 ms LFO lag softens square edges, and 30 ms depth/on lags soften switches.
SC reports base followedFreq and modulated oscFreq separately. Analysis uses the
latter when available; telemetry is control-rate data, not a measured spectrum.

Each effect has its own AngleMapper state and source/target. Coordinates use the
actual image aspect ratio and mirrored display: thumb → index, 0° right, +90° up.
Minimum separation rejects overlapping tips; shortest/cw/ccw interval and optional
180° fold resolve wrapping. Threshold/invert precede linear/power response, then
deadband and exponential time smoothing stabilize it. Invalid/lost hands target
zero; Rate modulation also fades depth to zero, and Drive modulation fades the
wet mix so biased Fuzz does not colour the sound after hand loss. A missing camera OSC stream is
handled by SC's modulation watchdog. Existing pinch-distance amplitude and
articulation are unchanged. Conversion is independent of the UI so a future
control-point curve editor can replace the response function.

The angle response model and time-domain LFO model are separate plots. They are
not fabricated scope signals. Preview updates are at most 10 Hz and skipped
when hidden; camera/OSC processing runs before drawing and does not wait for Qt.
Only the newest display frame is retained. [Timing evidence](performance-report.md).

## Distortion / Fuzz choices and sources

SC's [official operator reference](https://doc.sccode.org/Overviews/Operators.html)
provides tanh, distort, softclip and clipping operators. We chose normalized tanh
for Distortion: `tanh(input * drive) / tanh(drive)`, followed by tone low-pass,
level and wet/dry. It produces smooth symmetric saturation, rather than adding a
new plugin or changing Basic's existing Soft Clip.

Fuzz instead filters before saturation, adds a 0.35 bias, applies tanh, clips
asymmetrically to -0.55/+0.85, then removes DC and filters again. The asymmetry
and harder clipping produce a different transfer curve/harmonic balance.
[LeakDC](https://doc.sccode.org/Classes/LeakDC.html) supplies DC removal. Tone
filtering reduces high-frequency energy, but neither processor is oversampled;
it cannot guarantee alias-free audio. High Drive and high notes expose aliasing.
The final hard cap protects peaks, not perceived loudness or hearing level.

Delay uses the original delay controls with explicit stereo buffers, Phasor,
[BufRd cubic interpolation](https://doc.sccode.org/Classes/BufRd.html), BufWr,
filtered feedback (maximum 0.85) and DC/feedback peak protection. Reverb uses
[FreeVerb2](https://doc.sccode.org/Classes/FreeVerb2.html). No Thru input reaches
these stages. Final DC removal slightly changes phase even on the dry path.

### Actual signal checks and listening

`tools/verify_effects_signal.py` renders the production DSP using SC
[non-realtime synthesis](https://doc.sccode.org/Guides/Non-Realtime-Synthesis.html),
48 kHz stereo, and reads the resulting PCM. Eleven scenes cover Thru with all FX
enabled/changed, internal source, each key effect, bypass tails, Subtractive,
and 5 kHz/high-drive saturation. PANIC at 2 s is followed by node/buffer frees.
These are rendered signals, not Python-generated approximations of the effects.

| Measurement | Result on this machine |
| --- | --- |
| Thru left/right amplitude (input 0.07 / 0.05) | 0.06989 / 0.05007; fitted cross-channel component < 1e-16 |
| PANIC, all 11 scenes | PCM peak exactly 0 after mute |
| Distortion / Fuzz DC, steady low-tone test | about -1.5e-5 |
| Peak across scenes | <= 0.98002 (16-bit quantization of 0.98 cap) |
| Delay / Reverb bypass-tail RMS | 0.04453 / 0.01973 |
| Vibrato ±40 ct / 5 Hz, measured p05 / p95 | -40.27 / +40.92 ct |
| Tremolo depth 0.6, measured amplitude ratio | 0.4059 (nominal 0.4) |
| Equal-RMS Distortion / Fuzz waveform difference | 0.1296 normalized RMS |
| 5 kHz high-drive off-harmonic energy fraction | Distortion 0.000734; Fuzz 0.004683 |

The last metric excludes 5/10/15/20 kHz harmonic bands and DC. It is an
alias-plus-spurious proxy, not a complete alias-isolation measurement. The
processors demonstrably differ at matched RMS; no human listening comparison
was performed. CPU snapshots appear in the performance report and are not a
guarantee for all settings. Generated WAVs and `measurements.json` live in ignored
`analysis/effects-signal/`.

To compare by ear, run the renderer, then play `distortion-level-matched.wav` and
`fuzz-level-matched.wav` at the same playback volume; both normalize to RMS 0.08.
For live testing, use the same source, start quietly, disable all other FX, and
compare Distortion Drive 2/Tone 8000/Level 0.5/Mix 1 with Fuzz
Drive 8/Tone 4000/Level 0.4/Mix 1. Match perceived level with Level before judging
timbre, then repeat on low and high notes. These are test settings, not saved
factory patches. Listen for DC transients, aliasing and clicks on toggles/order.

## Patch migration

The existing Store writes Patch envelope v2 / schema v2; Layout stays v1. Patch
includes both probe banks, pitch/mapping, shared FX, per-effect angle configuration,
keys and serial order. Machine devices and Thru On/Level are excluded. Device
profiles and Thru level are stored separately by OS; On is never persisted.
Gate is always zero on recall. Unknown fields, invalid keys/order, nonfinite or
out-of-range values fail validation before altering the live settings.

Version 1 Patch Basic Delay/Reverb migrate to the common Effects. If the selected
probe was Subtractive, both migrated On flags stay OFF because those Basic FX
were previously unused. Original Basic FX are retained in `migration.basic_fx`
metadata, including former On flags. Shared values mirror the legacy Basic keys
for compatibility, so the metadata preserves the original independently. Common
FX now follow either source; exact sonic identity with the old internal feedback
implementation is not guaranteed. Files are not rewritten during read; save with
a new name to preserve a v1 original. Corrupt machine Audio Setup files are backed
up as `.invalid-<id>.json` only when an explicit Apply repairs them.

## Manual checks still required

- macOS Finder launch, executable permissions, Audio MIDI / Aggregate Device,
  actual iPad/Koala → UR44C stereo input/output and device removal during play.
- Human equal-level listening, extended two-hand sessions, physical audio latency
  and dropouts at the intended hardware buffer size.
- A second physical monitor, native Scope/FreqScope signal-content inspection and
  long sessions with repeated external SC server restarts.

## Verification record (2026-10-26, Windows)

- Python unittest suite: **52 passed**, including the prior mapping/shutdown/UI
  tests, angle/loss/independence, key focus/release, Patch migration, machine
  audio separation, Audio Setup Apply, duplicate activation, and an actual batch
  launch from a path containing spaces.
- SC lifecycle: passed full source compilation, production FX SynthDefs,
  modulation-loss safeguards, original input watchdog, resume and PANIC checks.
- Real SC / OSC: passed both parameter catalogs and common FX round trips,
  control-bus telemetry, actual bus order and source bypass, source switching,
  heartbeat mute, owned restart with unique nodes/handlers, unavailable-device
  refusal and explicit recovery. Production camera Start/Stop delivered 15
  640×480 frames through MediaPipe/display/OSC; this final run detected no hands.
  Controlled inputs separately test existing two-hand/octave/quantizer behavior.
- Production NRT signal checks: all 11 scenes passed, including node/buffer frees.
  Windows daily launcher and duplicate activation were observed; native UI
  screenshots confirmed the panels and Audio Setup. Subsequent Computer Use
  dialog-close input failed with a non-target-window coordinate error, so further
  native drag/resize interaction was not claimed. Qt rendering/layout tests pass.
- macOS launchers passed Bash syntax checking on Windows, and Git stores their
  executable bits/LF endings. This is not a macOS runtime or hardware test.
- Software timing: three conditions before/after, plus six simultaneous angle
  routes after. Raw reports and measurement caveats are in the performance report.

The native launcher fixture was closed after inspection. Test settings were
temporary; existing user Patch/Layout files were not overwritten by these tests.

### Startup-timeout follow-up (2026-10-26)

The reported production log showed language startup and device enumeration but
no audio configuration/boot request. The machine audio file did not exist.
The reproducible UI fault was dismissing first-run Audio Setup, then pressing
Start: an unconfigured server was treated as an in-progress boot and reported
`SC startup timed out` after 45 seconds while waiting for user selection.

Start now opens/reopens the same Audio Setup without starting a countdown when
selection is required, including after a failed boot. Apply/recovery leaves
performance muted and requires another explicit Start. Stop/PANIC also retains
an explicit queued audio-device transaction while cancelling performance
commands; previously it could discard that transaction and leave
`audio_requested=True` with no boot request. Urgent PANIC mute remains immediate.
Genuine timeouts identify language connection / audio boot / settings sync and
record audio status, pending transaction and SC log path in the launch log and UI.

Regression verification: **57 Python tests passed**. The real
`verify_regular_connection.py --first-run --camera` check passed first Start,
dialog dismissal/reopening, Apply followed by Stop while audio was queued,
muted readiness, existing probe/FX/restart tests, then explicit camera Start/Stop
(15 frames at 640×480, a hand detected in the final run). All use temporary
machine settings and a separate muted SC test port. User settings were not
automatically filled with a device choice. Relaunch the production UI to load
the fix, then select devices and Apply in Audio Setup.

日本語: 実装経路と自動検証を上に記録しています。ステレオ分離・FX・余韻・PANICはSCで
実際にレンダリングした信号から確認しました。iPad／UR44C・macOS、聴感比較、物理的な
手→出音遅延は未検証です。高Driveの歪みはエイリアシングを残し得ます。旧Patchは読み取り時に
移行し、元ファイルを書き換えません。Subtractive選択だった旧Patchで未使用Basic FXを
自動ONにせず、元の設定を移行メタデータへ残します。
