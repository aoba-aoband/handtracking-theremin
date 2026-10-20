"""Opt-in real SC/OSC check. Boots an owned, muted server; no camera required."""
from pathlib import Path
import sys
import time
import argparse
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from gui.regular.transport import Bridge
from gui.regular.catalog import CATALOG


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", action="store_true")
    parser.add_argument("--scopes", action="store_true", help="Open native SC signal windows briefly")
    parser.add_argument("--scope-seconds", type=float, default=12)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    bridge = Bridge(port=57122)
    from gui.regular.app import InstrumentWindow
    from gui.regular.state import Store
    temporary = tempfile.TemporaryDirectory()
    window = InstrumentWindow(store=Store(temporary.name), bridge=bridge)
    states, monitors = {}, {}
    bridge.state.connect(lambda probe, values: states.update({probe: values}))
    bridge.telemetry.connect(lambda probe, values: monitors.update({probe: values}))

    def wait(condition, timeout=25, send=True):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if send: bridge.tick()
            app.processEvents()
            if condition(): return
            time.sleep(.02)
        raise AssertionError("SC verification timed out; inspect logs/regular-sc.log")

    try:
        bridge.launch()
        wait(lambda: bridge.connected and "basic" in states and window.monitor and not bridge.busy)
        window.timer.stop()
        print("PASS cold UI startup, settings synchronization and real monitor reception")
        for probe in CATALOG:
            bridge.request("select", probe)
            wait(lambda: probe in states and not bridge.busy)
            bridge.request("set", probe, "filterCutoff", 3210)
            wait(lambda: abs(states[probe].get("filterCutoff", 0) - 3210) < .1)
            bridge.client.send_message("/sample/right/pitch/final_freq", 660.)
            wait(lambda: abs(monitors.get(probe, {}).get("followedFreq", 0) - 660) < 1)
            assert "effectiveCutoff" in monitors[probe] or "filterFreq" in monitors[probe]
            # Exercise every editable parameter through the real transaction path.
            expected = {}
            for key, spec in CATALOG[probe].items():
                if spec.kind == "readout": continue
                expected[key] = spec.default
                if key not in ("performanceGate", "monitorOn", "monitorRate", "outputLevel"):
                    expected[key] = spec.validate(min(spec.maximum, spec.default + (spec.step or .001)))
            expected.update(outputLevel=0, performanceGate=0, filterCutoff=3210)
            bridge.request("restore", probe, *[item for pair in expected.items() for item in pair])
            wait(lambda: not bridge.busy)
            wait(lambda: all(abs(states[probe].get(k, -999) - v) < max(.0001, abs(v) * 1e-6) for k, v in expected.items()))
            bridge.request("set", probe, "performanceGate", 1)
            wait(lambda: monitors[probe].get("performanceEnv", 0) > .05)
            wait(lambda: states[probe]["performanceGate"] == 0, timeout=5, send=False)
            print("PASS", probe, "UI communication-loss watchdog")
            bridge.panic()
            wait(lambda: not bridge.busy and states[probe]["performanceGate"] == 0)
            print("PASS", probe, "OSC round trip, actual server telemetry, panic")
        bridge.request("select", "basic")
        wait(lambda: not bridge.busy)
        assert states["basic"]["filterCutoff"] == 3210
        print("PASS probe settings retained across cleanup/switch")
        if args.camera:
            frames, errors = [], []
            # Exercise the same Start and display path as the production UI.
            window.start()
            worker = window.worker
            assert worker is not None, window.camera_status.text()
            worker.frame.connect(lambda image, features, events, fps: frames.append((image.size(), len(features), fps)))
            worker.failure.connect(errors.append)
            try:
                wait(lambda: (len(frames) >= 15 and window.camera_view.image is not None) or errors, timeout=25)
                assert not errors, errors
                assert "Camera running" in window.camera_status.text()
                print("PASS production Start + real camera + MediaPipe + displayed frames + OSC:", len(frames), "frames", frames[-1])
            finally:
                window.stop()
                wait(lambda: window.worker is None, timeout=7)
                assert window.camera_view.image is None
                print("PASS production Stop and camera cleanup")
        if args.scopes:
            bridge.request("scope")
            bridge.request("spectrum")
            wait(lambda: not bridge.busy)
            print("SC signal windows open for inspection", flush=True)
            duration = max(1, min(60, args.scope_seconds))
            until = time.monotonic() + duration
            wait(lambda: time.monotonic() >= until, timeout=duration + 3)
    finally:
        window.close()
        temporary.cleanup()


if __name__ == "__main__": main()
