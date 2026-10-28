"""Opt-in real SC/OSC check. Boots an owned, muted server; no camera required."""
from pathlib import Path
import sys
import time
import argparse
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from gui.regular.transport import Bridge, verification_port
from gui.regular.catalog import CATALOG


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", action="store_true")
    parser.add_argument("--first-run", action="store_true", help="Exercise first Start, dismissed Audio Setup, explicit Apply and silent waiting")
    parser.add_argument("--scopes", action="store_true", help="Open native SC signal windows briefly")
    parser.add_argument("--scope-seconds", type=float, default=12)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    bridge = Bridge(port=verification_port())
    print("Verification OSC port:",bridge.port,flush=True)
    from gui.regular.app import InstrumentWindow
    from gui.regular.state import Store
    temporary = tempfile.TemporaryDirectory()
    window = InstrumentWindow(store=Store(temporary.name), bridge=bridge)
    states, monitors = {}, {}
    fx_state, inspected, order_state = {}, {}, []
    bridge.fx_state.connect(fx_state.update)
    bridge.inspection.connect(inspected.update)
    bridge.order_changed.connect(lambda order: order_state.__setitem__(slice(None), order))
    bridge.state.connect(lambda probe, values: states.update({probe: values}))
    bridge.telemetry.connect(lambda probe, values: monitors.update({probe: values}))

    def wait(condition, timeout=25, send=True):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if send: bridge.tick()
            app.processEvents()
            if condition(): return
            time.sleep(.02)
        raise AssertionError(f"SC verification timed out; inspect {bridge.log_path}; state={bridge.audio_status}")

    try:
        if args.first_run:
            window.start()
            assert not window.start_requested and window.audio_dialog.isVisible()
            wait(lambda: bridge.connected and bridge.devices_received)
            assert bridge.audio_status["state"] == "unconfigured"
            window.audio_dialog.close()
            window.start()
            assert not window.start_requested and window.audio_dialog.isVisible()
            window.start_requested_at -= 46
            window.tick()
            assert "Audio Setup required" in window.camera_status.text() and window.worker is None
            window.audio_dialog.apply()
            assert window.machine_audio.load() == {"input":"none","output":None,"sample_rate":None}
            bridge.tick()  # Queue the explicit pre-boot choice before Stop.
            assert any(item[1] == "audio" for item in bridge.queue)
            window.stop()
            assert any(item[1] == "audio" for item in bridge.queue)
            wait(lambda: bridge.audio_ready and window.synced and not bridge.busy)
            assert not window.start_requested and window.worker is None
            assert states["basic"]["performanceGate"] == 0
            window.audio_dialog.close()
            print("PASS first Start / dismissed Audio Setup / explicit Apply / silent waiting without false timeout",flush=True)
        else:
            bridge.configure_audio({"input": "none", "output": None, "sample_rate": None})
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
        from gui.regular.effects import FX_SPECS
        expected_fx = {}
        for fx, specs in FX_SPECS.items():
            for key, spec in specs.items():
                value = spec.validate(min(spec.maximum, spec.default + (spec.step or .001)))
                expected_fx[fx + "." + key] = value
                bridge.request("fx", fx, key, value)
        wait(lambda: not bridge.busy)
        assert all(abs(fx_state[k]-v) < max(.0001,abs(v)*1e-6) for k,v in expected_fx.items())
        order = ["reverb", "delay", "fuzz", "distortion", "tremolo"]
        bridge.request("order", *order)
        wait(lambda: not bridge.busy and order_state == order)
        bridge.request("inspect")
        wait(lambda: not bridge.busy and "source.out" in inspected and "tremolo.out" in inspected)
        assert inspected["source.sharedFX"] == 1
        previous = inspected["source.out"]
        for fx in order:
            assert inspected[fx+".in"] == previous
            previous = inspected[fx+".out"]
        assert inspected["master.inA"] == previous and inspected["master.inB"] == previous
        assert inspected["chainCount"] == 1 and inspected["thruNode"] == -1
        assert inspected["master.mute"] == 1
        print("Source UGen graph:",inspected.get("sourceUGens"),flush=True)
        print("PASS every shared FX parameter, actual server bus order, internal Basic FX bypass, muted master")
        bridge.request("select", "subtractive")
        wait(lambda: not bridge.busy)
        assert all(abs(fx_state[k]-v) < max(.0001,abs(v)*1e-6) for k,v in expected_fx.items())
        bridge.request("select", "basic")
        wait(lambda: not bridge.busy)
        print("PASS shared FX retained across probe cleanup/switch")
        # Read the real server's node tree, independently of the UI's model.
        def node_tree():
            import socket
            from pythonosc.osc_message_builder import OscMessageBuilder
            from pythonosc.osc_packet import OscPacket
            query = OscMessageBuilder(address="/g_queryTree"); query.add_arg(0); query.add_arg(0)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                sock.settimeout(2)
                sock.sendto(query.build().dgram,("127.0.0.1",int(inspected["serverPort"])))
                packet=OscPacket(sock.recv(65536))
                values=packet.messages[0].message.params
            return [v for v in values if isinstance(v,str)]
        names=node_tree()
        assert names.count("basicOscProbe") == 1 and names.count("regularMaster") == 1
        assert all(names.count(name) == 1 for name in ("regularTremolo","regularDistortion","regularFuzz","regularDelay","regularReverb"))
        initial_generation = inspected["generation"]
        handler_count=inspected["handlerCount"]
        window.timer.start(100)
        # Keep this hardware check silent even while Gate is exercised later.
        for bank in window.settings["probes"].values(): bank["outputLevel"] = 0
        window.stop()
        bridge.configure_audio({"input":"none","output":None,"sample_rate":None})
        wait(lambda: bridge.audio_ready and bridge.audio_status["generation"] > initial_generation and window.synced and not bridge.busy,timeout=40)
        inspected.clear(); bridge.request("inspect")
        wait(lambda: not bridge.busy and "master.mute" in inspected and "tremolo.out" in inspected)
        assert inspected["handlerCount"] == handler_count
        assert inspected["master.mute"] == 1 and inspected["source.performanceGate"] == 0
        assert inspected["chainCount"] == 1 and inspected["thruNode"] == -1
        names=node_tree(); assert names.count("basicOscProbe")==1 and names.count("regularMaster")==1
        print("PASS real server restart, generation change, settings resync, unique handlers/nodes and silent waiting")
        bridge.configure_audio({"input":"Missing test device","output":None,"sample_rate":None})
        wait(lambda: bridge.audio_status["state"] == "missing-device")
        bridge.configure_audio({"input":"none","output":None,"sample_rate":None})
        wait(lambda: bridge.audio_ready and window.synced and not bridge.busy,timeout=40)
        print("PASS unavailable device refuses fallback; explicit reconfiguration recovers")
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
