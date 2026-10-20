import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase

from gui.regular.catalog import CATALOG, GROUPS, ROOT
from gui.regular.state import Store, initial_settings, validate_settings
from gui.regular.app import InstrumentWindow, STYLE
from tools.generate_regular_specs import generate
from src.pitch import midi_to_freq, NOTE_NAMES, SCALE_NAMES, PITCH_GUIDE_MODE_NAMES
from src.features import HandFeatures
from src.mapping import SampleMusicalMapper


class OfflineBridge(QObject):
    state = Signal(str, dict)
    telemetry = Signal(str, dict)
    error = Signal(str)
    connected = False
    busy = False

    def __init__(self):
        super().__init__()
        self.queue, self.requests = [], []

    def panic(self): self.queue.clear(); self.requests.append(("panic",))
    def request(self, *args): self.requests.append(args)
    def tick(self): pass
    def close(self): pass
    def launch(self): self.requests.append(("launch",))
    def send_many(self, events): pass


class FakeCamera(QObject):
    frame = Signal(object, object, object, float)
    failure = Signal(str)
    finished = Signal()

    def __init__(self, *args):
        super().__init__()
        self.running = False

    def start(self): self.running = True
    def isRunning(self): return self.running
    def requestInterruption(self): self.running = False; self.finished.emit()
    def wait(self, timeout): return not self.running


class RegularUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font = Path("C:/Windows/Fonts/segoeui.ttf")
        if font.exists(): QFontDatabase.addApplicationFont(str(font))
        cls.app.setStyle("Fusion"); cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bridge = OfflineBridge()
        self.window = InstrumentWindow(store=Store(self.tmp.name), bridge=self.bridge)
        self.window.timer.stop()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close(); self.app.processEvents(); self.tmp.cleanup()

    def test_source_catalog_is_complete_and_generated_specs_match(self):
        self.assertEqual({p: len(s) for p, s in CATALOG.items()}, {"basic": 46, "subtractive": 41})
        self.assertEqual(generate(), (ROOT / "sc/regular_specs.scd").read_text(encoding="utf-8"))
        for p in CATALOG:
            self.assertEqual(set(CATALOG[p]), {k for _, keys in GROUPS[p] for k in keys.split()})

    def test_defaults_and_all_pitch_options_are_preserved(self):
        w = self.window
        self.assertEqual(w.settings["mapping"]["pitch_min_freq"], 220)
        self.assertEqual(w.settings["mapping"]["pitch_root"], "A")
        for name, expected in (("Root", NOTE_NAMES), ("Scale", SCALE_NAMES), ("Guide Mode", PITCH_GUIDE_MODE_NAMES), ("Quantize", ("OFF", "ON"))):
            combo = w.pitch_refs[name]
            self.assertEqual([combo.itemText(i) for i in range(combo.count())], list(expected))
        self.assertEqual(w.pitch_refs["Min"][0].count(), 128)
        self.assertEqual(w.pitch_refs["Max"][0].count(), 128)

    def test_pitch_note_and_hz_are_independent_of_scale(self):
        w = self.window
        w.pitch_refs["Min"][0].setCurrentIndex(0)
        w.pitch_refs["Max"][0].setCurrentIndex(127)
        self.assertAlmostEqual(w.settings["mapping"]["pitch_min_freq"], midi_to_freq(0))
        self.assertAlmostEqual(w.settings["mapping"]["pitch_max_freq"], midi_to_freq(127))
        w.pitch_refs["Min"][1].setValue(123.45678)
        w.pitch_refs["Root"].setCurrentText("D#")
        w.pitch_refs["Scale"].setCurrentText("major")
        self.assertAlmostEqual(w.settings["mapping"]["pitch_min_freq"], 123.45678)
        w.range_changed("Min", 20000)
        self.assertAlmostEqual(w.settings["mapping"]["pitch_min_freq"], 123.45678)

    def test_harmonics_are_twelve_aligned_vertical_faders(self):
        refs = self.window.controls.refs
        faders = [refs[f"harmonic{i}"] for i in range(1, 13)]
        self.assertTrue(all(c.slider.orientation() == Qt.Orientation.Vertical for c in faders))
        self.assertEqual(len({c.mapTo(self.window.controls, c.rect().topLeft()).y() for c in faders}), 1)

    def test_probe_registry_and_readonly_values(self):
        self.window.probe_menu.setCurrentIndex(1)
        self.app.processEvents()
        self.assertEqual(set(self.window.controls.refs), set(CATALOG["subtractive"]))
        for key in ("osc1Wave", "osc2Wave"):
            control = self.window.controls.refs[key].control
            self.assertEqual([control.itemText(i) for i in range(control.count())], ["Saw", "Pulse", "Triangle"])
        self.assertEqual(self.window.controls.refs["articulationGate"].control.text(), "Not received")
        with self.assertRaises(ValueError): CATALOG["subtractive"]["articulationGate"].validate(1)

    def test_patch_and_layout_are_independent_and_recall_cannot_open_gate(self):
        w = self.window
        w.parameter_changed("filterCutoff", 2345)
        w.settings["probes"]["basic"]["performanceGate"] = 1
        w.patch_name.setText("My patch"); w.save_patch()
        w.docks["Analysis"].setFloating(True)
        w.docks["Analysis"].resize(620, 450)
        self.app.processEvents()
        w.layout_name.setText("My layout"); w.save_layout()
        w.parameter_changed("filterCutoff", 4000)
        w.recall_layout()
        self.assertEqual(w.settings["probes"]["basic"]["filterCutoff"], 4000)
        w.recall_patch()
        self.assertEqual(w.settings["probes"]["basic"]["filterCutoff"], 2345)
        self.assertEqual(w.settings["probes"]["basic"]["performanceGate"], 0)
        self.assertTrue(w.docks["Analysis"].isFloating())
        self.assertEqual(w.store.names("patches"), ["My patch"])
        self.assertEqual(w.store.names("layouts"), ["My layout"])

    def test_remote_settings_update_controls_and_offline_gate_does_not_queue(self):
        w = self.window; w.synced = True
        w.receive_state("basic", {"filterCutoff": 4321})
        self.assertEqual(w.controls.refs["filterCutoff"].number.value(), 4321)
        w.parameter_changed("performanceGate", 1)
        self.assertEqual(w.settings["probes"]["basic"]["performanceGate"], 0)
        self.assertNotIn(("set", "basic", "performanceGate", 1), self.bridge.requests)

    def test_patch_validation_rejects_nonfinite_and_readonly_values(self):
        settings = initial_settings()
        for value in (float("nan"), float("inf"), -1):
            settings["probes"]["basic"]["filterCutoff"] = value
            with self.assertRaises(ValueError): validate_settings(settings)
        settings = initial_settings()
        settings["probes"]["subtractive"]["articulationGate"] = 1
        with self.assertRaises(ValueError): validate_settings(settings)

    def test_envelope_updates_and_resize_render(self):
        w = self.window
        w.probe_menu.setCurrentIndex(1)
        w.parameter_changed("filterEnvAttack", .7)
        env = next(p for p in w.controls.plots if p.prefix == "filterEnv")
        self.assertAlmostEqual(env.values["filterEnvAttack"], .7)
        for width, height in ((1500, 950), (1050, 750)):
            w.resize(width, height); self.app.processEvents()
            self.assertFalse(w.grab().isNull())
            for module in w.controls.modules:
                self.assertGreaterEqual(module.height(), module.minimumSizeHint().height())

    def test_existing_handed_mapping_octave_and_quantization(self):
        right = HandFeatures("Right", .6, .5, .6, .6, .6, .5, .1, 21)
        left = HandFeatures("Left", .3, .4, .3, .5, .2, .4, .7, 21)
        mapper = SampleMusicalMapper({"pitch_min_freq": 220, "pitch_max_freq": 880, "pitch_root": "C", "pitch_scale": "major", "quantize_pitch": True})
        values = {e.address: e.value for e in mapper.map([left, right])}
        self.assertAlmostEqual(values["/sample/right/pitch/final_freq"], 440)
        self.assertEqual(values["/sample/left/pinch"], .7)
        self.assertEqual(values["/sample/left/tone/norm"], .3)
        from dataclasses import replace
        values = {e.address: e.value for e in mapper.map([left, replace(right, middle_tip_y=.4)])}
        self.assertAlmostEqual(values["/sample/right/pitch/final_freq"], 880)
        self.assertEqual(values["/sample/right/pitch/octave_shift"], 1)

    def test_oscillator_wave_rows_align_and_old_modules_are_hidden(self):
        old = list(self.window.controls.modules)
        self.window.probe_menu.setCurrentIndex(1); self.app.processEvents()
        self.assertTrue(all(m.isHidden() for m in old))
        refs = self.window.controls.refs
        ys = [refs[key].mapTo(self.window.controls, refs[key].rect().topLeft()).y() for key in ("osc1Wave", "osc2Wave")]
        self.assertLessEqual(abs(ys[0] - ys[1]), 2)

    def test_latest_camera_frame_does_not_build_a_display_backlog(self):
        from PySide6.QtGui import QImage
        for i in range(10): self.window.enqueue_frame(QImage(100, 100, QImage.Format.Format_RGB888), [], [], i)
        self.window.consume_frame()
        self.assertEqual(self.window.camera_view.fps, 9)
        self.assertIsNone(self.window.latest_frame)

    @patch("gui.regular.app.CameraWorker", FakeCamera)
    def test_start_during_sc_startup_is_retained_until_synchronization(self):
        w = self.window
        w.start()
        self.assertTrue(w.start_requested)
        self.assertIsNone(w.worker)
        self.assertIn(("launch",), self.bridge.requests)
        self.bridge.connected = True
        self.bridge.busy = True
        w.tick()
        self.assertTrue(w.start_requested)
        self.assertIsNone(w.worker)
        self.assertIn("pending", w.camera_status.text())
        self.bridge.busy = False
        w.tick()
        worker = w.worker
        self.assertTrue(worker.isRunning())
        self.assertFalse(w.start_requested)
        self.assertEqual(w.settings["probes"]["basic"]["performanceGate"], 0)
        w.start()
        self.assertIs(w.worker, worker)
        self.assertEqual(w.settings["probes"]["basic"]["performanceGate"], 0)
        from PySide6.QtGui import QImage
        w.on_frame(QImage(100, 100, QImage.Format.Format_RGB888), [], [], 30)
        self.assertEqual(w.settings["probes"]["basic"]["performanceGate"], 1)

    @patch("gui.regular.app.CameraWorker", FakeCamera)
    def test_pending_start_is_cancelled_by_stop_panic_or_probe_switch(self):
        w = self.window
        for cancel in (w.stop, w.panic, lambda: w.select_probe(1)):
            w.start()
            self.assertTrue(w.start_requested)
            cancel()
            self.assertFalse(w.start_requested)
            self.assertEqual(w.camera_status.text(), "Camera stopped")
        self.bridge.connected = True
        w.tick()
        self.assertIsNone(w.worker)

    def test_camera_failure_remains_visible_after_worker_cleanup(self):
        w = self.window
        w.camera_failure("Camera 0 could not be opened")
        w.camera_finished()
        w.tick()
        self.assertIn("Camera 0 could not be opened", w.camera_status.text())
        self.assertEqual(w.settings["probes"]["basic"]["performanceGate"], 0)

    def test_pending_start_timeout_and_launch_failure_do_not_open_gate(self):
        w = self.window
        with patch.object(self.bridge, "launch", side_effect=RuntimeError("SC missing")):
            w.start()
        self.assertFalse(w.start_requested)
        self.assertIn("SC launch failed", w.camera_status.text())
        w.start()
        w.start_requested_at -= 46
        w.tick()
        self.assertFalse(w.start_requested)
        self.assertIsNone(w.worker)
        self.assertIn("timed out", w.camera_status.text())


if __name__ == "__main__": unittest.main()
