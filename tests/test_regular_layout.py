"""Functional presentation regressions using real Qt widgets and isolated state."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from copy import deepcopy
import tempfile
import unittest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QScrollArea
from test_regular_ui import OfflineBridge
from gui.regular.app import InstrumentWindow, STYLE
from gui.regular.state import Store


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
        cls.app.setStyle("Fusion"); cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.bridge=OfflineBridge()
        self.w=InstrumentWindow(store=Store(self.tmp.name),bridge=self.bridge)
        self.w.timer.stop(); self.w.show(); self.settle()

    def settle(self):
        for _ in range(15): self.app.processEvents()

    def tearDown(self):
        self.w.close(); self.settle(); self.tmp.cleanup()

    def test_effects_grow_and_shrink_without_changing_order_or_values(self):
        w=self.w; panel=w.effects_panel; dock=w.docks["Effects"]
        state=deepcopy(w.settings); requests=list(self.bridge.requests)
        dock.setFloating(True)
        for width,columns in ((400,1),(800,2),(1200,3),(400,1)):
            dock.resize(width,800); self.settle()
            self.assertEqual(panel.rack.columns,columns)
            self.assertEqual(panel.area.horizontalScrollBar().maximum(),0)
            for card in panel.modules.values():
                self.assertLessEqual(card.width(),480)
                self.assertGreaterEqual(card.height(),card.minimumSizeHint().height())
            self.assertEqual([card.effect for card in panel.rack.cards],["vibrato",*state["effects"]["order"]])
        self.assertEqual(w.settings,state); self.assertEqual(self.bridge.requests,requests)

    def test_multiple_details_expand_without_overlap_and_preserve_values(self):
        panel=self.w.effects_panel; self.w.docks["Effects"].setFloating(True)
        self.w.docks["Effects"].resize(400,800); self.settle()
        for name in ("vibrato","tremolo"):
            panel.modules[name].details.set_expanded(True)
        self.settle()
        cards=panel.rack.cards
        for card in cards:
            self.assertGreaterEqual(card.height(),card.minimumSizeHint().height())
        for a,b in zip(cards,cards[1:]): self.assertLess(a.geometry().bottom(),b.y())
        for name in ("vibrato","tremolo"):
            module=panel.modules[name]
            self.assertTrue(module.advanced.isVisible())
            module.mapping_refs["smoothing"].setValue(.25)
            self.assertEqual(self.w.settings["effects"]["mappings"][name]["smoothing"],.25)

    def test_pin_lock_visibility_and_details_round_trip_without_audio_commands(self):
        w=self.w; dock=w.docks["Camera"]
        dock.setFloating(True); dock.resize(500,600); dock.move(40,50)
        dock.set_pinned(True); dock.set_locked(True)
        w.docks["Analysis"].hide()
        w.effects_panel.modules["delay"].details.set_expanded(True)
        self.settle(); saved=w.layout_data(); state=deepcopy(w.settings)
        requests=list(self.bridge.requests)
        dock.set_locked(False); dock.set_pinned(False); dock.setFloating(False)
        w.docks["Analysis"].show(); w.effects_panel.modules["delay"].details.set_expanded(False)
        w.apply_layout(saved); self.settle()
        self.assertTrue(dock.isFloating()); self.assertTrue(dock.pinned); self.assertTrue(dock.locked)
        self.assertTrue(dock.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(w.docks["Analysis"].isHidden())
        self.assertTrue(w.effects_panel.modules["delay"].details.toggle.isChecked())
        self.assertEqual(w.settings,state); self.assertEqual(self.bridge.requests,requests)
        before=dock.pos(); dock.move(before+QPoint(60,60)); self.settle()
        self.assertEqual(dock.pos(),before)
        dock.set_locked(False); dock.setFloating(False); self.settle()
        self.assertFalse(dock.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_old_layout_and_offscreen_panel_recovery(self):
        w=self.w; saved=w.layout_data()
        for key in ("panels","effect_details","diagnostics"): saved.pop(key)
        w.apply_layout(saved); self.settle()
        self.assertTrue(all(not dock.isHidden() and not dock.pinned for dock in w.docks.values()))
        dock=w.docks["Effects"]; dock.setFloating(True); dock.move(-20000,-20000)
        dock.set_locked(True); dock.recover(); self.settle()
        self.assertTrue(any(screen.availableGeometry().contains(dock.frameGeometry().topLeft()) for screen in self.app.screens()))
        self.assertTrue(dock.locked)
        dock.hide(); dock.bring_forward(); self.settle(); self.assertFalse(dock.isHidden())

    def test_invalid_layout_rolls_back_panel_options_and_details(self):
        w=self.w; dock=w.docks["Effects"]
        dock.setFloating(True); dock.set_pinned(True); dock.set_locked(True)
        w.effects_panel.modules["delay"].details.set_expanded(True)
        self.settle(); saved=w.layout_data(); invalid=deepcopy(saved)
        invalid["floating"]["Effects"]=[1,2]
        with self.assertRaises(TypeError): w.apply_layout(invalid)
        self.settle()
        self.assertTrue(dock.isFloating() and dock.locked and dock.pinned)
        self.assertTrue(w.effects_panel.modules["delay"].details.toggle.isChecked())
        self.assertEqual(w.layout_data()["panels"],saved["panels"])

    def test_camera_settings_wrap_with_left_and_right_preserved(self):
        w=self.w; dock=w.docks["Camera"]; dock.setFloating(True)
        w.camera_settings_toggle.click()
        for width in (420,800,420):
            dock.resize(width,760); self.settle()
            self.assertEqual(w.camera_settings_area.horizontalScrollBar().maximum(),0)
            left=w.mapping_refs["threshold"].mapTo(w.camera_settings_content,QPoint()).x()
            right=w.pitch_refs["Root"].mapTo(w.camera_settings_content,QPoint()).x()
            self.assertLess(left,right)
        w.pitch_refs["Max"][1].setValue(12500)
        self.assertEqual(w.settings["mapping"]["pitch_max_freq"],12500)

    def test_local_transport_only_appears_when_floating(self):
        for dock in self.w.docks.values():
            bars=dock.widget().findChildren(QWidget,"localTransport")
            self.assertEqual(len(bars),1); self.assertTrue(bars[0].isHidden())
            dock.setFloating(True); self.settle(); self.assertFalse(bars[0].isHidden())
            dock.setFloating(False); self.settle(); self.assertTrue(bars[0].isHidden())

    def test_monitor_is_readonly_and_clears_when_measurements_expire(self):
        w=self.w; self.bridge.connected=True; w.synced=True; w.last_connected=True
        w.settings["probes"]["basic"]["monitorOn"]=1
        w.receive_monitor("basic",{"effectiveCutoff":1234,"followedFreq":440})
        w.tick(); self.assertEqual(w.monitor_table.rowCount(),2)
        self.assertIn("440.000 Hz",w.monitor_table.item(0,1).text())
        self.assertEqual(w.primary_values.item(0,1).text(),"440.000 Hz")
        self.assertEqual(w.primary_values.item(2,2).text(),"Measured")
        w.monitor_at-=10; w.tick(); self.assertEqual(w.monitor_table.rowCount(),0)
        self.assertEqual(w.primary_values.item(0,2).text(),"No data")
        self.assertEqual(w.primary_values.item(1,2).text(),"Setting")
        self.assertEqual(w.primary_values.item(2,1).text(),"—")

    def test_save_uses_active_name_not_unrecalled_selection(self):
        w=self.w
        for category in ("Patch","Layout"):
            directory="patches" if category=="Patch" else "layouts"
            field,menu=(w.patch_name,w.patch_menu) if category=="Patch" else (w.layout_name,w.layout_menu)
            save=w.save_patch if category=="Patch" else w.save_layout
            field.setText("Active"); save()
            field.setText("Other"); save()
            field.setText("Active"); save()
            before=w.store.read(directory,"Other")
            menu.setCurrentText("Other")
            w.parameter_changed("filterCutoff",2345)
            w.docks["Analysis"].hide()
            w.save_named(category)
            self.assertEqual(field.text(),"Active")
            self.assertEqual(w.store.read(directory,"Other"),before)

    def test_effect_reorder_keeps_identifiers_separate_from_numbered_labels(self):
        w=self.w; panel=w.effects_panel
        before=deepcopy(w.settings["effects"]["values"])
        panel.order.setCurrentRow(0); panel.move_effect(1); self.settle()
        self.assertEqual(w.settings["effects"]["order"][:2],["distortion","tremolo"])
        self.assertEqual(panel.order.item(0).text(),"1 · Distortion")
        self.assertEqual(panel.rack.cards[1].effect,"distortion")
        self.assertEqual(w.settings["effects"]["values"],before)

    def test_hold_cannot_survive_pin_or_layout_change(self):
        w=self.w; dock=w.docks["Effects"]
        w.settings["effects"]["keys"]["tremolo"]={"key":"T","mode":"hold"}
        saved=w.layout_data()
        for operation in (lambda:dock.setFloating(True),lambda:dock.set_pinned(True),lambda:w.apply_layout(saved)):
            w.setFocus(); QTest.keyPress(w,Qt.Key.Key_T)
            self.assertEqual(w.settings["effects"]["values"]["tremolo"]["on"],1)
            operation(); self.settle()
            self.assertFalse(w.effect_keys.held)
            self.assertEqual(w.settings["effects"]["values"]["tremolo"]["on"],0)
            self.assertFalse(w.thru_on)
            self.assertTrue(all(bank["performanceGate"]==0 for bank in w.settings["probes"].values()))

    def test_controls_resize_keeps_comparisons_and_contains_wide_sections(self):
        w=self.w; dock=w.docks["Controls"]; dock.setFloating(True)
        for probe in (0,1):
            w.select_probe(probe)
            for width in (800,420,1200,420):
                dock.resize(width,850); self.settle()
                self.assertEqual(w.controls_area.horizontalScrollBar().maximum(),0)
                if probe == 0 and width >= 800:
                    for area in w.controls.findChildren(QScrollArea):
                        self.assertEqual(area.horizontalScrollBar().maximum(),0)
                if probe == 1:
                    refs=w.controls.refs
                    self.assertEqual(refs["osc1Wave"].mapTo(w.controls,QPoint()).y(),refs["osc2Wave"].mapTo(w.controls,QPoint()).y())
                    left=refs["filterCutoff"].mapTo(w.controls,QPoint())
                    right=refs["filterEnvAttack"].mapTo(w.controls,QPoint())
                    if width >= 800: self.assertEqual(left.y(),right.y())
                    else: self.assertGreater(right.y(),left.y())

    def test_status_keeps_errors_and_does_not_report_stale_audio_ready(self):
        w=self.w
        self.bridge.audio_status={"state":"ready","input_channels":2}
        self.bridge.connected=False
        w.update_system_status()
        self.assertIn("Audio: disconnected",w.system_status.text())
        self.assertEqual(w.effects_panel.thru_status.text(),"Input: not ready")
        w.show_error("Test connection error")
        w.statusBar().showMessage("Timing log saved",100)
        w.docks["Camera"].setFloating(True); w.docks["Camera"].set_pinned(True)
        w.open_status(); self.settle()
        self.assertTrue(w.status_dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertIn("Test connection error",w.error_detail.toPlainText())
        self.assertFalse(w.error_banner.isHidden())

    def test_numeric_extremes_fit_without_reducing_precision(self):
        w=self.w
        for probe in (0,1):
            w.select_probe(probe); self.settle()
            controls=list(w.controls.refs.values())
            controls += [control for module in w.effects_panel.modules.values() for control in module.module.controls.values()]
            for control in controls:
                if control.number is None: continue
                for value in (control.spec.minimum,control.spec.maximum):
                    control.show_value(value)
                    edit=control.number.lineEdit()
                    self.assertGreaterEqual(edit.contentsRect().width(),edit.fontMetrics().horizontalAdvance(edit.text()),control.spec.key)


if __name__=="__main__": unittest.main()
