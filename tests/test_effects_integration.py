import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from gui.regular.app import InstrumentWindow
from gui.regular.audio_setup import AudioSetup, MachineAudio, validate_audio, available, device_warnings
from gui.regular.effects import initial_effects, validate_effects, FX_SPECS
from gui.regular.performance import PerformanceRecorder
from gui.regular.state import Store, initial_settings, validate_settings
from gui.regular.camera import CameraWorker
from src.angle_mapping import pinch_angle, angle_normalized, AngleMapper
from src.features import HandFeatures
from tools.generate_effect_specs import generate
from test_regular_ui import OfflineBridge


def hand(angle=0, side="Left", width=640, height=480):
    radians=math.radians(angle)
    return HandFeatures(side, .5-math.cos(radians)*100/width, .5-math.sin(radians)*100/height,
                        .5,.5,.5,.5,.2,21)


class AngleTests(unittest.TestCase):
    def test_mirrored_angle_and_aspect_ratio(self):
        for width,height in ((640,480),(1920,1080),(480,800)):
            for angle in (-135,-90,-45,0,45,90,135):
                self.assertAlmostEqual(pinch_angle(hand(angle,width=width,height=height),width,height),angle)
        self.assertIsNone(pinch_angle(replace(hand(),index_tip_x=.5,index_tip_y=.5),640,480))
        self.assertIsNone(pinch_angle(replace(hand(),thumb_tip_x=float("nan")),640,480))

    def test_direction_wrap_fold_threshold_inversion_and_curves(self):
        c=initial_effects()["mappings"]["tremolo"]; c.update(threshold=0)
        self.assertEqual(angle_normalized(90,c),0)
        self.assertEqual(angle_normalized(0,c),1)
        self.assertAlmostEqual(angle_normalized(45,c),.5)
        c.update(zero=170,maximum=-170)
        self.assertAlmostEqual(angle_normalized(180,c),.5)
        c.update(zero=90,maximum=0,fold=True)
        self.assertEqual(angle_normalized(180,c),1)
        c.update(fold=False,curve="slow",bend=2)
        self.assertAlmostEqual(angle_normalized(45,c),.25)
        c["curve"]="fast"; self.assertAlmostEqual(angle_normalized(45,c),.75)
        c.update(curve="linear",threshold=.6)
        self.assertEqual(angle_normalized(45,c),0)
        c.update(threshold=0,invert=True)
        self.assertEqual(angle_normalized(90,c),1)
        c.update(invert=False,zero=0,maximum=90,direction="clockwise")
        self.assertAlmostEqual(angle_normalized(-135,c),.5)

    def test_deadband_and_loss_return_smoothly_to_zero(self):
        c=initial_effects()["mappings"]["vibrato"]; c.update(smoothing=.1,threshold=0)
        mapper=AngleMapper()
        first=mapper.update("v",hand(0),640,480,c,1/30)
        self.assertGreater(first["normalized"],0); self.assertLess(first["normalized"],1)
        jitter=mapper.update("v",hand(.2),640,480,c,1/30)
        self.assertEqual(mapper.states["v"]["angle"],first["angle"])
        loss=mapper.update("v",None,640,480,c,1/30)
        self.assertFalse(loss["valid"]); self.assertGreater(loss["normalized"],0)
        self.assertLess(loss["normalized"],jitter["normalized"])
        for _ in range(100): loss=mapper.update("v",None,640,480,c,1/30)
        self.assertLess(loss["normalized"],1e-10)

    def test_per_effect_hand_sources_and_existing_pinch_coexist(self):
        from src.mapping import SampleMusicalMapper
        effects=initial_effects()
        effects["mappings"]["tremolo"].update(source="left",threshold=0,smoothing=.005)
        effects["mappings"]["vibrato"].update(source="right",threshold=0,smoothing=.005)
        left,right=hand(0),hand(90,"Right")
        packets=[]
        worker=CameraWorker(0,"unused",initial_settings()["mapping"],lambda events:None)
        worker.configure_effects(effects,lambda *args:packets.append(args))
        worker.process_angles([left,right],640,480,.1)
        values={row[0]:row[2] for row in packets}
        self.assertAlmostEqual(values["tremolo"],.5,places=6)
        self.assertAlmostEqual(values["vibrato"],0,places=6)
        events={e.address:e.value for e in SampleMusicalMapper().map([left,right])}
        self.assertEqual(events["/sample/left/pinch"],left.pinch)
        self.assertIn("/sample/left/articulation/gate",events)


class PersistenceTests(unittest.TestCase):
    def test_panic_cancels_gate_but_preserves_explicit_audio_boot_request(self):
        from collections import deque
        from unittest.mock import Mock
        from gui.regular.transport import Bridge
        # Use the production transaction methods without opening sockets/SC.
        bridge=Mock()
        bridge.queue=deque(); bridge.next_id=0; bridge.session="test"; bridge.sent_at=99
        bridge.request=lambda op,*args:Bridge.request(bridge,op,*args)
        bridge.request("set","basic","performanceGate",1)
        bridge.request("audio","__NONE__","__DEFAULT__",0)
        audio=bridge.queue[-1]
        bridge.request("fx","fuzz","on",1)
        Bridge.panic(bridge)
        self.assertEqual([item[1] for item in bridge.queue],["audio","panic"])
        self.assertEqual(bridge.queue[0],audio)
        self.assertGreater(int(bridge.queue[-1][0].split(":")[1]),int(audio[0].split(":")[1]))
        bridge.client.send_message.assert_any_call("/sample/panic",1)
        Bridge.panic(bridge)
        self.assertEqual([item[1] for item in bridge.queue],["audio","panic"])

    def test_legacy_patch_migrates_basic_fx_once(self):
        data=initial_settings(); data.pop("schema_version"); data.pop("effects")
        data["probes"]["basic"].update(delayOn=1,delayMix=.42,reverbOn=1,reverbMix=.21)
        patch=validate_settings(data)
        self.assertEqual(patch["effects"]["values"]["delay"]["mix"],.42)
        self.assertEqual(patch["effects"]["values"]["reverb"]["mix"],.21)
        self.assertEqual(patch["schema_version"],2)
        self.assertEqual(validate_settings(patch),patch)

    def test_old_subtractive_patch_does_not_enable_unused_basic_fx(self):
        data=initial_settings(); data.pop("schema_version"); data.pop("effects"); data.pop("migration")
        data["probe"]="subtractive"
        data["probes"]["basic"].update(delayOn=1,delayMix=.7)
        patch=validate_settings(data)
        self.assertEqual(patch["effects"]["values"]["delay"]["on"],0)
        self.assertAlmostEqual(patch["effects"]["values"]["delay"]["mix"],.7)
        self.assertEqual(patch["migration"]["basic_fx"]["delayOn"],1)

    def test_extended_patch_round_trip_and_corrupt_data(self):
        data=initial_settings()
        data["effects"]["mappings"]["fuzz"].update(source="right",maximum=-90,curve="slow")
        data["effects"]["keys"]["fuzz"]={"key":"Ctrl+G","mode":"hold"}
        data["effects"]["order"].reverse()
        expected=validate_settings(data)
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory); store.write("patches","test",data)
            self.assertEqual(validate_settings(store.read("patches","test")),expected)
            content=json.loads((Path(directory)/"patches/test.json").read_text())
            self.assertEqual(content["version"],2)
        for mutate in (lambda d:d.update(unknown=1),lambda d:d["probes"].update(other={}),lambda d:d["effects"]["values"]["fuzz"].update(drive=float("nan")),
                       lambda d:d["effects"].update(order=["vibrato"]),lambda d:d["effects"]["mappings"]["fuzz"].update(source="other")):
            invalid=deepcopy(data); mutate(invalid)
            with self.assertRaises(ValueError): validate_settings(invalid)

    def test_reserved_duplicate_and_invalid_keys(self):
        for key in ("F5","F6","F12","not a real key"):
            data=initial_effects(); data["keys"]["fuzz"]["key"]=key
            with self.assertRaises(ValueError): validate_effects(data)
        data=initial_effects()
        data["keys"]["fuzz"]["key"]="Ctrl+G"; data["keys"]["delay"]["key"]="Ctrl+G"
        with self.assertRaises(ValueError): validate_effects(data)

    def test_os_specific_machine_devices_and_missing_device(self):
        with tempfile.TemporaryDirectory() as directory:
            windows=MachineAudio(directory,"Windows"); mac=MachineAudio(directory,"Darwin")
            a={"input":"none","output":"Windows WASAPI : Speaker","sample_rate":48000}
            b={"input":"iPad","output":"Steinberg UR44C","sample_rate":None}
            windows.save(a); mac.save(b)
            self.assertEqual(windows.load(),a); self.assertEqual(mac.load(),b)
            self.assertFalse(available(a,{"input":[],"output":[]}))
            windows.save_thru_level(.7); self.assertEqual(windows.thru_level(),.7)
            self.assertIn("different Windows APIs",device_warnings(dict(input="MME : Mic",output="ASIO : Out",sample_rate=None),"Windows"))
            self.assertIn("Audio MIDI",device_warnings(b,"Darwin"))

    def test_effect_specs_and_statistics(self):
        target=Path(__file__).resolve().parents[1]/"sc/regular_effect_specs.scd"
        self.assertEqual(generate(),target.read_text())
        recorder=PerformanceRecorder(capacity=3)
        for value in range(5): recorder.control({"mapping_ms":float(value)})
        recorder.overwrite(); recorder.shown({"display_age_ms":12.})
        report=recorder.summary()
        self.assertEqual(report["control_frames"],3)
        self.assertEqual(report["timings_ms"]["mapping_ms"]["median"],3)
        self.assertEqual(report["timings_ms"]["mapping_ms"]["max"],4)
        self.assertEqual(report["display_frames_superseded"],1)

    def test_corrupt_machine_config_is_preserved_on_explicit_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            machine=MachineAudio(directory,"Windows")
            machine.path.write_text('{broken')
            with self.assertRaises(ValueError): machine.load()
            machine.save(dict(input="none",output=None,sample_rate=None))
            self.assertEqual(machine.load()["input"],"none")
            self.assertEqual(len(list(Path(directory).glob("audio-setup.invalid-*.json"))),1)


class ExtendedUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.bridge=OfflineBridge()
        self.window=InstrumentWindow(store=Store(self.temp.name),bridge=self.bridge)
        self.window.timer.stop(); self.window.show(); self.app.processEvents()
    def tearDown(self):
        self.window.close(); self.app.processEvents(); self.temp.cleanup()

    def test_effects_dock_controls_and_period(self):
        w=self.window; self.assertIn("Effects",w.docks)
        self.assertEqual(set(w.effects_panel.modules),set(FX_SPECS))
        w.effect_changed("vibrato","rate",8)
        module=w.effects_panel.modules["vibrato"]
        self.assertAlmostEqual(module.period.value(),125)
        module.period.setValue(250)
        self.assertAlmostEqual(w.settings["effects"]["values"]["vibrato"]["rate"],4)
        w.docks["Effects"].setFloating(True); w.docks["Effects"].resize(560,850)
        self.app.processEvents(); self.assertFalse(w.docks["Effects"].grab().isNull())
        w.effect_changed("delay","mix",.3)
        w.select_probe(1)
        self.assertEqual(w.settings["effects"]["values"]["delay"]["mix"],.3)
        self.assertEqual(w.settings["probes"]["basic"]["delayMix"],.3)
        self.assertFalse(w.thru_on)

    def test_audio_setup_enumeration_missing_selection_and_muted_apply(self):
        w=self.window; b=self.bridge
        b.devices={"input":["MME : Input"],"output":["MME : Output"]}
        b.devices_received=True; b.connected=True
        b.audio_status={"state":"unconfigured"}; b.audio_ready=False
        applied=[]; b.configure_audio=lambda config:applied.append(config)
        dialog=AudioSetup(w)
        try:
            self.assertTrue(dialog.apply_button.isEnabled())
            dialog.populate(dict(input="Missing",output=None,sample_rate=None))
            self.assertFalse(dialog.apply_button.isEnabled())
            self.assertIn("unavailable",dialog.status.text())
            dialog.input.setCurrentIndex(dialog.input.findData("MME : Input"))
            dialog.output.setCurrentIndex(dialog.output.findData("MME : Output"))
            w.thru_on=True
            dialog.apply()
            self.assertEqual(len(applied),1)
            self.assertEqual(applied[0]["input"],"MME : Input")
            self.assertFalse(w.thru_on)
            self.assertEqual(w.machine_audio.load(),applied[0])
            self.assertEqual(w.settings["probes"]["basic"]["performanceGate"],0)
            with unittest.mock.patch("gui.regular.audio_setup.platform.system",return_value="Darwin"):
                dialog.rate.setCurrentIndex(dialog.rate.findData(48000))
                self.assertIsNone(dialog.current()["sample_rate"])
        finally: dialog.close()

    def test_start_after_dismissing_first_audio_setup_does_not_time_out(self):
        w=self.window; b=self.bridge
        b.connected=True; b.audio_ready=False; b.audio_requested=False
        b.audio_status={"state":"unconfigured"}
        b.devices_received=True; b.devices={"input":[],"output":["MME : Output"]}
        # Reproduce the user's first-run path: enumerate, close the prompt,
        # then press Start again without applying an audio configuration.
        w.receive_devices()
        dialog=w.audio_dialog
        self.assertIsNotNone(dialog)
        dialog.close()
        w.start()
        self.assertFalse(w.start_requested)
        self.assertIs(w.audio_dialog,dialog)
        self.assertTrue(dialog.isVisible())
        w.start_requested_at-=46
        w.tick()
        self.assertNotIn("timed out",w.camera_status.text())
        self.assertIn("Audio Setup required",w.camera_status.text())
        self.assertIsNone(w.worker)
        self.assertEqual(w.settings["probes"]["basic"]["performanceGate"],0)

    def test_first_start_opens_audio_setup_before_language_is_ready(self):
        w=self.window; b=self.bridge
        b.audio_ready=False; b.audio_requested=False
        b.audio_status={"state":"disconnected"}
        b.devices_received=False; b.devices={"input":[],"output":[]}
        w.start()
        self.assertFalse(w.start_requested)
        self.assertIsNotNone(w.audio_dialog)
        self.assertTrue(w.audio_dialog.isVisible())
        self.assertFalse(w.audio_dialog.apply_button.isEnabled())
        self.assertIn(("launch",),b.requests)

    def test_failed_audio_start_returns_to_setup_with_cause(self):
        w=self.window; b=self.bridge
        b.connected=True; b.audio_ready=False; b.audio_requested=True
        b.audio_status={"state":"failed","error":"Selected audio device is busy"}
        b.devices_received=True; b.devices={"input":[],"output":[]}
        w.start()
        self.assertFalse(w.start_requested)
        self.assertTrue(w.audio_dialog.isVisible())
        self.assertIn("device is busy",w.audio_dialog.status.text())

    def test_real_startup_timeouts_report_the_waiting_stage(self):
        w=self.window; b=self.bridge
        w.timer.stop()
        for connected,audio_ready,state,stage in (
            (False,False,"disconnected","SC language connection"),
            (True,False,"booting","audio server boot"),
            (True,True,"ready","SC settings")):
            b.connected=connected; b.audio_ready=audio_ready; b.audio_status={"state":state}
            b.queue=[("test:1","select",("basic",))]
            w.start_requested=True
            w.startup_timeout()
            self.assertFalse(w.start_requested)
            self.assertIn(stage,w.camera_status.text())
            self.assertIn("pending=select",w.camera_status.toolTip())
            self.assertIn("audio="+state,w.statusBar().currentMessage())
            self.assertIsNone(w.worker)

    def key(self,kind,key=Qt.Key.Key_G,repeat=False):
        event=QKeyEvent(kind,key,Qt.KeyboardModifier.NoModifier,"g",repeat,1)
        return self.window.effect_keys.eventFilter(self.window,event)

    def test_key_repeat_text_entry_hold_and_focus_loss(self):
        w=self.window; w.settings["effects"]["keys"]["fuzz"]={"key":"G","mode":"toggle"}
        w.camera_view.setFocus(); self.app.processEvents()
        self.assertTrue(self.key(QEvent.Type.KeyPress)); self.assertEqual(w.settings["effects"]["values"]["fuzz"]["on"],1)
        self.key(QEvent.Type.KeyPress,repeat=True)
        self.assertEqual(w.settings["effects"]["values"]["fuzz"]["on"],1)
        self.key(QEvent.Type.KeyRelease)
        w.patch_menu.setFocus(); self.app.processEvents()
        self.assertFalse(self.key(QEvent.Type.KeyPress))
        w.patch_menu.clearFocus(); w.setFocus(); self.app.processEvents()
        w.settings["effects"]["keys"]["fuzz"]["mode"]="hold"
        w.effect_changed("fuzz","on",0)
        self.key(QEvent.Type.KeyPress)
        self.assertEqual(w.settings["effects"]["values"]["fuzz"]["on"],1)
        w.effect_keys.eventFilter(w,QEvent(QEvent.Type.ApplicationDeactivate))
        self.assertEqual(w.settings["effects"]["values"]["fuzz"]["on"],0)
        self.assertFalse(w.effect_keys.held)

    def test_hold_release_after_modifier_released_first(self):
        w=self.window; w.setFocus(); self.app.processEvents()
        w.settings["effects"]["keys"]["fuzz"]={"key":"Ctrl+G","mode":"hold"}
        down=QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_G,Qt.KeyboardModifier.ControlModifier,"g")
        up=QKeyEvent(QEvent.Type.KeyRelease,Qt.Key.Key_G,Qt.KeyboardModifier.NoModifier,"g")
        self.assertTrue(w.effect_keys.eventFilter(w,down))
        self.assertEqual(w.settings["effects"]["values"]["fuzz"]["on"],1)
        self.assertTrue(w.effect_keys.eventFilter(w,up))
        self.assertEqual(w.settings["effects"]["values"]["fuzz"]["on"],0)
        self.assertFalse(w.effect_keys.held)

    def test_patch_layout_and_machine_thru_are_separate(self):
        w=self.window
        w.effect_mapping_changed("tremolo","source","left")
        w.effect_order_changed(list(reversed(w.settings["effects"]["order"])))
        w.patch_name.setText("Extended"); w.save_patch()
        saved=json.loads((Path(self.temp.name)/"patches/Extended.json").read_text())
        self.assertNotIn("audio",saved["data"]); self.assertNotIn("thru",saved["data"])
        w.effect_changed("tremolo","depth",.2); w.recall_patch()
        self.assertEqual(w.settings["effects"]["values"]["tremolo"]["depth"],.5)
        self.assertEqual(w.settings["probes"]["basic"]["performanceGate"],0)
        self.assertIn("Effects",w.docks)

    def test_single_instance_activates_existing_window(self):
        from gui.regular.single_instance import SingleInstance
        calls=[]
        class Existing:
            def showNormal(self): calls.append("show")
            def raise_(self): calls.append("raise")
            def activateWindow(self): calls.append("activate")
        one=SingleInstance(65001); two=SingleInstance(65001)
        try:
            self.assertTrue(one.acquire()); one.attach(Existing())
            self.assertFalse(two.acquire())
            for _ in range(3): self.app.processEvents()
            self.assertEqual(calls,["show","raise","activate"])
        finally: one.close(); two.close()


if __name__ == "__main__": unittest.main()
