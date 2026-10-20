# Regular UI

Launch from the repository root:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe main.py ui
```

Click **Start** (F5). If SC is not connected, it launches SC and displays
**Start pending** until the connection and settings synchronization finish.
It then opens the camera and opens the performance gate after the first frame.
**Launch SC** can also prepare SC separately. **Stop** cancels a pending Start,
closes the gate and stops the
camera. **PANIC** immediately mutes the owned synth, clears pending commands,
and closes the performance gate; it leaves the camera running. Only an explicit
Start/Gate action unmutes. Patch recall, reset, reconnect and probe switching
remain silent.

Camera startup errors remain visible above the camera area until the next Start.
If SC is not ready within 45 seconds, Start is cancelled with a timeout message.

F5 = Start, F6 = Stop, F12 = PANIC throughout the application, including floating
panels. Plain Space, Escape and number-entry keys are left to their widgets.
Each panel also has these three buttons.

Double-click a panel title or use its Float button to detach it. Drag its title
to dock it again, or resize/move the floating window onto another monitor.
Tabbed docking is disabled. Camera Settings can be hidden to enlarge the video.
Small panels retain scrollbars instead of compressing or hiding parameters.

Patch Save/Recall stores the named settings for both probes, pitch and mapping.
Layout Save/Recall separately stores docking, floating geometry and Camera
Settings visibility. The last layout is also restored on the next launch.
Files live in ignored `user_data/`; no named factory patches are installed.
Neither sample HTML values nor its Left/Right/Full layout controls are imported.

## Connection and ownership

The UI launches an owned sclang and scsynth with OSC language port **57121**
and an automatically allocated audio-server port. It uses the existing sample
OSC addresses and existing DSP SynthDefs. The original `hands --send-osc` route
still uses its configured port (57120 by default). Only use one active performance
sender for a given receiver.

For an existing SC IDE session, evaluate `sc/regular_bridge.scd` there and launch
`main.py ui --ui-sc-port 57120`. The UI closes only its own launched processes;
closing an externally connected UI sends PANIC without quitting the IDE/server.
Launch SC auto-discovery currently supports the usual Windows Program Files
installation. Other installation locations can use the existing-session method.

Connection loss from the UI mutes the synth after 2 seconds. The existing
left-pinch watchdog additionally releases amp after one second without pinch
data. Probe changes use the existing cleanup hook and retain separate settings.
Commands are acknowledged/retried, and duplicate requests are ignored by SC.

The existing `gui/theremin_gui.py` sounddevice launcher is independent and was
not integrated or changed for this UI.

## Parameters and analysis

`catalog.py` reads defaults, slider ranges/steps/scales and toggles from the SC
sources. Modules are a separate ordered registry. Basic has 46 parameters;
Subtractive has 41, including tracker/SC readouts. SC's internal mute control is
not a patch parameter. Formal names remain on widget tooltips.

`sc/regular_specs.scd` is the bridge's generated validation table. After changing
source parameter contracts, run `python tools/generate_regular_specs.py` and
update the module registry if new parameters were introduced. The parity test
detects drift. `monitorRate` uses the server's 0.1–30 Hz range.

The Filter response is an explicitly labelled RLPF approximation. Its shared
Hz/dB axes show the configured pitch range, manual cutoff, server-reported
followed frequency and server-reported effective cutoff. No effective value is
invented while disconnected or before a monitor packet. Monitor OFF and low
monitor rates are respected. Envelope plots illustrate timing with an explicitly
illustrative hold; they are not measured envelopes.

Scope/FreqScope buttons open **native SuperCollider signal windows**, not model
waveforms embedded into Analysis. They observe the real audio server. Telemetry
is control-rate server data, not a spectrum measurement.

## Validation

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
& 'C:\Program Files\SuperCollider-3.14.1\sclang.exe' -D (Join-Path $PWD 'tests\sc_input_lifecycle.scd')
.\venv\Scripts\python.exe tools\verify_regular_connection.py --camera
```

Add `--scopes` to open the native SC signal windows briefly during that check.

The opt-in connection check tests cold UI startup with a separate muted server, exercises every
editable parameter on both probes, receives actual followed frequency/cutoff,
tests communication-loss muting and probe-state retention, and optionally acquires
camera frames through the actual tracker and OSC output. It does not save images.

Verified on this machine: real SC boot/OSC/control telemetry, all editable
parameter round trips, timeout/PANIC, camera acquisition (640×480), model inference,
patch/layout tests, rendered layouts and native Stethoscope/Freq Analyzer window
creation. Capturing those SC windows for visual inspection timed out at Computer
Use app approval, so their displayed signal contents were not visually verified.
Real hand performance, listening tests, and moving windows onto a second physical
monitor still require manual checking. The camera check had no detected hands;
mapping/octave/quantization behavior was exercised with controlled feature inputs.
