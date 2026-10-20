"""English, dockable production UI for the existing instrument pipeline."""
from copy import deepcopy
import base64
import sys
import time
import threading

from PySide6.QtCore import Qt, QTimer, QByteArray, QRect, QPoint
from PySide6.QtGui import QAction, QKeySequence, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QLabel, QComboBox, QDoubleSpinBox, QLineEdit,
    QMessageBox, QSizePolicy, QLayout,
)

from src.pitch import NOTE_NAMES, SCALE_NAMES, PITCH_GUIDE_MODE_NAMES, midi_to_freq, freq_to_midi, format_midi_note
from src.mapping import build_articulation_runtime_config
from .catalog import CATALOG, GROUPS, Parameter, ROOT
from .state import initial_settings, validate_settings, Store
from .transport import Bridge
from .camera import CameraWorker
from .widgets import Module, ParameterControl, CameraView, FilterPlot, EnvelopePlot, button

STYLE = """
QWidget { background:#202728; color:#e5ece9; font-family:'Segoe UI'; font-size:13px; }
QMainWindow { background:#14191a; }
QDockWidget { font-weight:600; }
QDockWidget::title { background:#2d3637; padding:7px; }
QWidget#module { border:1px solid #445252; border-radius:4px; }
QWidget#module QWidget { border:0; }
QLabel#heading { color:#90cfb8; font-weight:600; padding-bottom:5px; }
QPushButton, QComboBox, QDoubleSpinBox, QLineEdit { background:#182020; border:1px solid #445252; border-radius:3px; min-height:27px; padding:0 6px; }
QPushButton:hover { background:#354644; }
QPushButton:checked { background:#206b58; color:#ffffff; }
QPushButton#panic { color:#ffbd99; border-color:#ad7153; font-weight:600; }
QSlider::groove:horizontal { height:4px; background:#445252; border-radius:2px; }
QSlider::handle:horizontal { width:12px; margin:-5px 0; background:#90cfb8; border-radius:4px; }
QSlider::groove:vertical { width:4px; background:#445252; }
QSlider::handle:vertical { height:12px; margin:0 -5px; background:#90cfb8; border-radius:4px; }
QScrollArea { border:0; }
QScrollBar { background:#182020; }
QToolTip { color:#e5ece9; background:#182020; border:1px solid #90cfb8; }
"""


def scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


class ControlsArea(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.grid = QGridLayout(self)
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.modules, self.refs, self.plots = [], {}, []
        self.columns = 0
        self.build()

    def build(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.modules, self.refs, self.plots = [], {}, []
        probe = self.window.settings["probe"]
        values = self.window.settings["probes"][probe]
        for title, keys in GROUPS[probe]:
            plot = None
            prefix = {"Filter Env": "filterEnv", "Articulation": "articulation", "Performance / Output": "performance"}.get(title)
            if prefix:
                plot = EnvelopePlot(prefix, values)
                self.plots.append(plot)
            module = Module(title, [CATALOG[probe][k] for k in keys.split()], values, self.window.parameter_changed, title == "Harmonics", plot)
            self.modules.append(module)
            self.refs.update(module.controls)
        self.columns = 0
        self.reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        columns = max(1, min(3, self.width() // 380))
        if columns == self.columns:
            return
        self.columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        row, col = 0, 0
        for module in self.modules:
            if module.title in ("Additive", "Harmonics"):
                if col:
                    row, col = row + 1, 0
                self.grid.addWidget(module, row, 0, 1, columns)
                row += 1
            else:
                self.grid.addWidget(module, row, col, Qt.AlignmentFlag.AlignTop)
                col += 1
                if col == columns:
                    row, col = row + 1, 0
        for i in range(3):
            self.grid.setColumnStretch(i, 1 if i < columns else 0)


class InstrumentWindow(QMainWindow):
    def __init__(self, camera_index=0, model_path=None, mapping=None, store=None, bridge=None):
        super().__init__()
        self.setWindowTitle("Handtrack • Regular")
        self.resize(1500, 950)
        self.settings = initial_settings()
        if mapping:
            self.settings["mapping"].update(mapping)
        self.settings = validate_settings(self.settings)
        self.store = store or Store()
        self.bridge = bridge or Bridge()
        self.camera_index = camera_index
        self.model_path = str(model_path or ROOT / "models/hand_landmarker.task")
        if not __import__('pathlib').Path(self.model_path).is_absolute():
            self.model_path = str(ROOT / self.model_path)
        self.worker = None
        self.camera_stopping = False
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.shutting_down = False
        self.monitor = {}
        self.monitor_at = 0
        self.synced = False
        self.last_connected = False
        self.camera_start_pending = False
        self.start_requested = False
        self.start_requested_at = 0
        self.camera_error = None
        self.setDockOptions(QMainWindow.DockOption.AllowNestedDocks | QMainWindow.DockOption.AnimatedDocks)
        central = QWidget()
        central.setMaximumSize(0, 0)
        self.setCentralWidget(central)
        self.make_menu()
        self.docks = {}
        camera = self.make_camera()
        controls = self.make_controls()
        analysis = self.make_analysis()
        for name, content in (("Camera", camera), ("Controls", controls), ("Analysis", analysis)):
            dock = QDockWidget(name, self)
            dock.setObjectName(name)
            dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
            dock.setWidget(content)
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea if name != "Controls" else Qt.DockWidgetArea.RightDockWidgetArea, dock)
            self.docks[name] = dock
        self.splitDockWidget(self.docks["Camera"], self.docks["Analysis"], Qt.Orientation.Vertical)
        self.resizeDocks([self.docks["Camera"], self.docks["Controls"]], [690, 810], Qt.Orientation.Horizontal)
        self.resizeDocks([self.docks["Camera"], self.docks["Analysis"]], [570, 290], Qt.Orientation.Vertical)
        self.bridge.state.connect(self.receive_state)
        self.bridge.telemetry.connect(self.receive_monitor)
        self.bridge.error.connect(self.show_error)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.consume_frame)
        self.frame_timer.start(33)
        self.restore_session_layout()

    def make_menu(self):
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(6, 4, 6, 4)
        self.patch_name = QLineEdit(); self.patch_name.setPlaceholderText("Patch name"); self.patch_name.setMaximumWidth(140)
        self.patch_menu = QComboBox(); self.patch_menu.setMinimumWidth(110)
        self.layout_name = QLineEdit(); self.layout_name.setPlaceholderText("Layout name"); self.layout_name.setMaximumWidth(140)
        self.layout_menu = QComboBox(); self.layout_menu.setMinimumWidth(110)
        for widget in (QLabel("Patch"), self.patch_name, button("Save", self.save_patch), self.patch_menu, button("Recall", self.recall_patch), QLabel("Layout"), self.layout_name, button("Save", self.save_layout), self.layout_menu, button("Recall", self.recall_layout)):
            row.addWidget(widget)
        row.addStretch()
        self.setMenuWidget(bar)
        self.refresh_saved_menus()
        for name, shortcut, callback in (("Start", "F5", self.start), ("Stop", "F6", self.stop), ("PANIC", "F12", self.panic)):
            action = QAction(name, self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            action.triggered.connect(callback)
            self.addAction(action)

    def transport_bar(self):
        widget = QWidget()
        row = QHBoxLayout(widget); row.setContentsMargins(6, 4, 6, 4)
        for text, callback in (("Start · F5", self.start), ("Stop · F6", self.stop), ("PANIC · F12", self.panic)):
            b = button(text, callback)
            if text.startswith("PANIC"):
                b.setObjectName("panic")
            row.addWidget(b)
        row.addStretch()
        return widget

    def make_camera(self):
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.transport_bar())
        self.camera_status = QLabel("Camera stopped")
        toggle_row = QHBoxLayout()
        toggle_row.addWidget(self.camera_status, 1)
        self.camera_settings_toggle = button("Settings", lambda: self.camera_settings_area.setVisible(self.camera_settings_toggle.isChecked()))
        self.camera_settings_toggle.setCheckable(True); self.camera_settings_toggle.setChecked(True)
        toggle_row.addWidget(self.camera_settings_toggle)
        layout.addLayout(toggle_row)
        self.camera_view = CameraView(self.settings); layout.addWidget(self.camera_view, 1)
        settings = QWidget(); columns = QHBoxLayout(settings)
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Left • Mapping"))
        mapping = self.settings["mapping"]
        self.mapping_refs = {}
        for key, title, value, lo, hi, step, unit in (
            ("threshold", "Threshold", mapping["articulation_gate_on_threshold"], 0, 1, .01, ""),
            ("width", "Hysteresis", mapping["articulation_gate_on_threshold"] - mapping["articulation_gate_off_threshold"], 0, 1, .01, ""),
            ("release", "Hand Loss", mapping["articulation_hand_loss_release_seconds"] * 1000, 0, 2000, 1, "ms"),
        ):
            spec = Parameter(key, value, lo, hi, step, unit=unit)
            control = ParameterControl(spec)
            control.layout().setSpacing(4)
            control.findChild(QLabel).setMinimumWidth(70)
            control.slider.setMinimumWidth(32)
            control.number.setMinimumWidth(62); control.number.setMaximumWidth(72)
            # These are mapping settings, not renamed synth parameters.
            control.findChild(QLabel).setText(title)
            control.changed.connect(self.mapping_changed)
            ll.addWidget(control); self.mapping_refs[key] = control
        ll.addStretch()
        right = QWidget(); rl = QGridLayout(right); rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("Right • Pitch Settings"), 0, 0, 1, 3)
        self.pitch_refs = {}
        for row, (key, options, value) in enumerate((
            ("Root", NOTE_NAMES, mapping["pitch_root"]),
            ("Scale", SCALE_NAMES, mapping["pitch_scale"]),
            ("Guide Mode", PITCH_GUIDE_MODE_NAMES, self.settings["guide_mode"]),
            ("Quantize", ("OFF", "ON"), "ON" if mapping["quantize_pitch"] else "OFF"),
        ), 1):
            combo = QComboBox(); combo.addItems(options); combo.setCurrentText(value)
            combo.currentTextChanged.connect(lambda value, key=key: self.pitch_changed(key, value))
            rl.addWidget(QLabel(key), row, 0); rl.addWidget(combo, row, 1, 1, 2)
            self.pitch_refs[key] = combo
        for row, side in enumerate(("Min", "Max"), 5):
            note = QComboBox(); note.addItems([format_midi_note(i) for i in range(128)])
            hz = QDoubleSpinBox(); hz.setRange(midi_to_freq(0), midi_to_freq(127)); hz.setDecimals(5); hz.setSingleStep(.001); hz.setSuffix(" Hz"); hz.setKeyboardTracking(False)
            freq = mapping[f"pitch_{side.lower()}_freq"]
            hz.setValue(freq); note.setCurrentIndex(round(freq_to_midi(freq)))
            note.currentIndexChanged.connect(lambda value, side=side: self.range_changed(side, midi_to_freq(value)))
            hz.valueChanged.connect(lambda value, side=side: self.range_changed(side, value))
            rl.addWidget(QLabel(side), row, 0); rl.addWidget(note, row, 1); rl.addWidget(hz, row, 2)
            self.pitch_refs[side] = (note, hz)
        columns.addWidget(left, 1); columns.addWidget(right, 1)
        settings.setMinimumWidth(560)
        settings_area = scroll(settings); settings_area.setMinimumHeight(245); settings_area.setMaximumHeight(310)
        layout.addWidget(settings_area)
        self.camera_settings_area = settings_area
        return panel

    def make_controls(self):
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.transport_bar())
        header = QHBoxLayout()
        header.addWidget(QLabel("Probe"))
        self.probe_menu = QComboBox(); self.probe_menu.addItems(("Basic / Additive Probe", "Subtractive Probe"))
        self.probe_menu.setToolTip("Select the complete synthesis and processing path")
        self.probe_menu.currentIndexChanged.connect(self.select_probe)
        header.addWidget(self.probe_menu, 1)
        header.addWidget(button("Reset Defaults", self.reset_defaults))
        header.addWidget(button("Launch SC", self.launch_sc))
        layout.addLayout(header)
        self.path_label = QLabel(); self.path_label.setWordWrap(True); layout.addWidget(self.path_label)
        self.connection = QLabel("SC disconnected • settings are local"); layout.addWidget(self.connection)
        self.controls = ControlsArea(self); layout.addWidget(scroll(self.controls), 1)
        self.set_path_label()
        return panel

    def make_analysis(self):
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.transport_bar())
        content = QWidget(); body = QVBoxLayout(content)
        self.filter_plot = FilterPlot(self.settings); body.addWidget(self.filter_plot)
        self.monitor_label = QLabel("SC monitor • not received"); self.monitor_label.setWordWrap(True); body.addWidget(self.monitor_label)
        scopes = QHBoxLayout()
        scopes.addWidget(button("Open Scope (SC signal)", lambda: self.open_scope("scope")))
        scopes.addWidget(button("Open FreqScope (SC signal)", lambda: self.open_scope("spectrum")))
        body.addLayout(scopes)
        note = QLabel("Scope / FreqScope open native SC signal views. Filter and envelope curves are calculation models.")
        note.setWordWrap(True); body.addWidget(note)
        layout.addWidget(scroll(content), 1)
        return panel

    def set_path_label(self):
        self.path_label.setText({
            "basic": "Base sine + additive → Soft Clip → Filter → Delay → Reverb → Output",
            "subtractive": "Oscillators / Sub / Noise → RLPF → Pinch Amp → Articulation → Performance Gate → Output",
        }[self.settings["probe"]])

    def open_scope(self, kind):
        if self.bridge.connected:
            self.bridge.request(kind)
        else:
            self.show_error("SC is disconnected; no signal is available.")

    def reset_defaults(self):
        probe = self.settings["probe"]
        self.panic()
        self.settings["probes"][probe] = initial_settings()["probes"][probe]
        self.controls.build()
        self.synced = False
        if self.bridge.connected:
            self.sync_backend()

    def parameter_changed(self, key, value):
        probe = self.settings["probe"]
        spec = CATALOG[probe][key]
        value = spec.validate(value)
        values = self.settings["probes"][probe]
        values[key] = value
        if key in ("toneMinCutoff", "toneMaxCutoff"):
            if key == "toneMinCutoff" and value > values["toneMaxCutoff"]:
                values["toneMaxCutoff"] = value
            elif key == "toneMaxCutoff" and value < values["toneMinCutoff"]:
                values["toneMinCutoff"] = value
        if key == "performanceGate" and value:
            # A disconnected / recalled gate must never be queued for later.
            if not self.bridge.connected:
                values[key] = 0
                self.show_error("SC is disconnected. Launch SC before opening Gate.")
            else:
                self.bridge.request("set", probe, key, value)
        elif self.bridge.connected:
            self.bridge.request("set", probe, key, value)
        self.refresh_controls()

    def mapping_changed(self, key, value):
        values = {k: c.number.value() for k, c in self.mapping_refs.items()}
        values[key] = value
        config = build_articulation_runtime_config(values["threshold"], values["width"], values["release"])
        self.settings["mapping"].update(config)
        self.sync_mapping()
        self.apply_mapping()

    def sync_mapping(self):
        m = self.settings["mapping"]
        for key, val in (("threshold", m["articulation_gate_on_threshold"]), ("width", m["articulation_gate_on_threshold"] - m["articulation_gate_off_threshold"]), ("release", m["articulation_hand_loss_release_seconds"] * 1000)):
            self.mapping_refs[key].show_value(val)

    def pitch_changed(self, key, value):
        mapping = self.settings["mapping"]
        if key == "Guide Mode":
            self.settings["guide_mode"] = value
        else:
            mapping[{"Root": "pitch_root", "Scale": "pitch_scale", "Quantize": "quantize_pitch"}[key]] = (value == "ON") if key == "Quantize" else value
        self.apply_mapping()

    def range_changed(self, side, freq):
        mapping = self.settings["mapping"]
        key = f"pitch_{side.lower()}_freq"
        valid = midi_to_freq(0) <= freq <= midi_to_freq(127)
        valid = valid and (freq < mapping["pitch_max_freq"] if side == "Min" else freq > mapping["pitch_min_freq"])
        if valid:
            mapping[key] = freq
            self.apply_mapping()
        else:
            self.statusBar().showMessage("Min must be below Max. Range: MIDI 0–127.", 6000)
        self.sync_pitch()

    def sync_pitch(self):
        m = self.settings["mapping"]
        for key, val in (("Root", m["pitch_root"]), ("Scale", m["pitch_scale"]), ("Guide Mode", self.settings["guide_mode"]), ("Quantize", "ON" if m["quantize_pitch"] else "OFF")):
            combo = self.pitch_refs[key]; combo.blockSignals(True); combo.setCurrentText(val); combo.blockSignals(False)
        for side in ("Min", "Max"):
            note, hz = self.pitch_refs[side]
            freq = m[f"pitch_{side.lower()}_freq"]
            for widget in (note, hz): widget.blockSignals(True)
            note.setCurrentIndex(round(freq_to_midi(freq))); hz.setValue(freq)
            for widget in (note, hz): widget.blockSignals(False)

    def apply_mapping(self):
        if self.worker:
            self.worker.configure(self.settings["mapping"])
        self.camera_view.update(); self.filter_plot.update()

    def select_probe(self, index):
        self.panic()
        self.settings["probe"] = ("basic", "subtractive")[index]
        self.monitor, self.monitor_at = {}, 0
        self.controls.build(); self.set_path_label()
        self.synced = False
        if self.bridge.connected:
            self.sync_backend()

    def sync_backend(self):
        self.bridge.request("select", self.settings["probe"])
        for probe, values in self.settings["probes"].items():
            values["performanceGate"] = 0
            pairs = [item for key, value in values.items() if key != "performanceGate" for item in (key, value)]
            self.bridge.request("restore", probe, *pairs)
        self.synced = True

    def launch_sc(self):
        if not self.bridge.connected:
            try:
                self.bridge.launch()
                self.statusBar().showMessage("Starting SC • inspect logs/regular-sc.log if connection fails", 15000)
            except Exception as exc:
                self.show_error(str(exc))
                return False
        return True

    def start(self):
        if not self.bridge.connected or not self.synced or self.bridge.busy:
            if not self.start_requested:
                self.start_requested_at = time.monotonic()
            self.start_requested = True
            self.camera_error = None
            self.camera_status.setText("Start pending • waiting for SC")
            if not self.bridge.connected and not self.launch_sc():
                self.start_requested = False
                self.camera_status.setText("SC launch failed • see status message")
            return
        self.start_requested = False
        if self.worker and self.worker.isRunning():
            if self.camera_stopping:
                self.show_error("Waiting for camera to stop.")
                return
            if self.camera_start_pending:
                return
            self.parameter_changed("performanceGate", 1)
            return
        if self.worker is not None:
            self.show_error("Waiting for camera cleanup.")
            return
        self.bridge.panic()
        self.worker = CameraWorker(self.camera_index, self.model_path, self.settings["mapping"], self.bridge.send_many)
        self.worker.frame.connect(self.enqueue_frame, Qt.ConnectionType.DirectConnection)
        self.worker.failure.connect(self.camera_failure)
        self.worker.finished.connect(self.camera_finished)
        self.camera_start_pending = True
        self.camera_error = None
        self.camera_stopping = False
        self.camera_status.setText("Starting camera…")
        self.worker.start()

    def on_frame(self, image, features, events, fps):
        self.camera_view.present(image, features, events, fps)
        self.camera_status.setText("Camera running • left mapping / right pitch")
        if self.camera_start_pending:
            self.camera_start_pending = False
            self.parameter_changed("performanceGate", 1)

    def enqueue_frame(self, image, features, events, fps):
        # Tracker/OSC keep running immediately; the GUI only consumes the latest
        # frame instead of building a queue when painting or resizing is slow.
        with self.frame_lock:
            self.latest_frame = (image, features, events, fps)

    def consume_frame(self):
        with self.frame_lock:
            frame, self.latest_frame = self.latest_frame, None
        if frame is not None:
            self.on_frame(*frame)

    def camera_failure(self, message):
        self.panic()
        self.camera_error = message
        self.camera_status.setText("Camera error • " + message)
        self.show_error(message)

    def camera_finished(self):
        self.camera_start_pending = False
        self.camera_stopping = False
        with self.frame_lock:
            self.latest_frame = None
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        self.camera_status.setText("Camera error • " + self.camera_error if self.camera_error else "Camera stopped")
        self.camera_view.image = None
        self.camera_view.update()

    def stop(self):
        self.panic()
        if self.worker:
            self.camera_stopping = True
            self.worker.requestInterruption()

    def panic(self):
        was_waiting = self.start_requested
        self.start_requested = False
        self.camera_start_pending = False
        if was_waiting and self.worker is None:
            self.camera_status.setText("Camera stopped")
        self.bridge.panic()
        for values in self.settings["probes"].values():
            values["performanceGate"] = 0
        if hasattr(self, "controls"):
            self.refresh_controls()

    def receive_state(self, probe, values):
        if probe not in CATALOG:
            return
        # Keep local edits while their acknowledged transaction is pending.
        pending = self.bridge.busy or not self.synced
        for key, value in values.items():
            if key in self.settings["probes"][probe] and not pending:
                self.settings["probes"][probe][key] = value
        if probe == self.settings["probe"]:
            for key, control in self.controls.refs.items():
                if CATALOG[probe][key].kind == "readout":
                    control.show_value(values.get(key))
        self.refresh_controls()

    def receive_monitor(self, probe, values):
        if probe == self.settings["probe"]:
            self.monitor, self.monitor_at = values, time.monotonic()

    def refresh_controls(self):
        probe = self.settings["probe"]
        for key, control in self.controls.refs.items():
            if CATALOG[probe][key].kind != "readout":
                control.show_value(self.settings["probes"][probe][key])
        for plot in self.controls.plots:
            plot.update()
        if hasattr(self, "filter_plot"):
            self.filter_plot.update()

    def tick(self):
        self.bridge.tick()
        connected = self.bridge.connected
        if connected and not self.last_connected:
            requested, requested_at = self.start_requested, self.start_requested_at
            self.panic(); self.synced = False
            self.start_requested, self.start_requested_at = requested, requested_at
            if requested:
                self.camera_status.setText("Start pending • synchronizing SC")
        if connected and not self.synced:
            self.sync_backend()
        if not connected and self.last_connected:
            self.panic(); self.synced = False
        self.last_connected = connected
        if self.start_requested:
            if time.monotonic() - self.start_requested_at > 45:
                self.panic()
                self.camera_status.setText("SC startup timed out • see logs/regular-sc.log")
            elif connected and self.synced and not self.bridge.busy:
                self.start()
        camera_state = "camera running" if self.worker and self.worker.isRunning() else "camera stopped"
        self.connection.setText("SC connected • synchronizing" if connected and self.bridge.busy else "SC connected • " + camera_state if connected else "SC disconnected • settings are local")
        values = self.settings["probes"][self.settings["probe"]]
        fresh_seconds = max(1, 3 / max(.1, values["monitorRate"]))
        fresh = connected and values["monitorOn"] and time.monotonic() - self.monitor_at < fresh_seconds
        self.filter_plot.fresh_seconds = fresh_seconds
        self.filter_plot.monitor = self.monitor if fresh else {}
        self.filter_plot.received = self.monitor_at if fresh else 0
        self.filter_plot.update()
        if fresh:
            self.monitor_label.setText("SC monitor • server reports\n" + "    |    ".join(f"{key}: {value:.3f}" for key, value in self.monitor.items()))
        else:
            self.monitor_label.setText("SC monitor • not received" if connected else "SC disconnected • no measurements")
            if not connected:
                for key, control in self.controls.refs.items():
                    if CATALOG[self.settings["probe"]][key].kind == "readout":
                        control.show_value(None)

    def show_error(self, message):
        self.statusBar().showMessage(message, 12000)

    def refresh_saved_menus(self):
        for category, combo in (("patches", self.patch_menu), ("layouts", self.layout_menu)):
            current = combo.currentText(); combo.clear(); combo.addItems(self.store.names(category)); combo.setCurrentText(current)

    def save_patch(self):
        try:
            self.store.write("patches", self.patch_name.text(), validate_settings(self.settings))
            self.refresh_saved_menus(); self.patch_menu.setCurrentText(self.patch_name.text().strip())
        except Exception as exc: self.show_error(str(exc))

    def recall_patch(self):
        try:
            candidate = validate_settings(self.store.read("patches", self.patch_menu.currentText()))
            self.panic()
            # Preserve references used by plots and the camera widget.
            self.settings.clear(); self.settings.update(candidate)
            self.probe_menu.blockSignals(True); self.probe_menu.setCurrentIndex(("basic", "subtractive").index(candidate["probe"])); self.probe_menu.blockSignals(False)
            self.controls.build(); self.set_path_label(); self.sync_pitch(); self.sync_mapping(); self.apply_mapping()
            self.monitor, self.monitor_at = {}, 0
            self.synced = False
            if self.bridge.connected: self.sync_backend()
        except Exception as exc: self.show_error(str(exc))

    def layout_data(self):
        return {
            "geometry": bytes(self.saveGeometry().toBase64()).decode(),
            "state": bytes(self.saveState(1).toBase64()).decode(),
            "camera_settings": self.camera_settings_toggle.isChecked(),
            "floating": {name: list(dock.geometry().getRect()) for name, dock in self.docks.items() if dock.isFloating()},
        }

    def apply_layout(self, data):
        geometry = QByteArray.fromBase64(data["geometry"].encode())
        state = QByteArray.fromBase64(data["state"].encode())
        if not self.restoreGeometry(geometry) or not self.restoreState(state, 1):
            raise ValueError("Invalid layout")
        self.camera_settings_toggle.setChecked(data.get("camera_settings", True))
        self.camera_settings_area.setVisible(self.camera_settings_toggle.isChecked())
        for name, coords in data.get("floating", {}).items():
            if name in self.docks:
                rect = QRect(*[int(v) for v in coords])
                if any(screen.availableGeometry().intersects(rect) for screen in QApplication.screens()):
                    self.docks[name].setGeometry(rect)
        # Recover floating windows if a previously used monitor is absent.
        for dock in self.docks.values():
            if dock.isFloating() and not any(screen.availableGeometry().intersects(dock.frameGeometry()) for screen in QApplication.screens()):
                rect = QApplication.primaryScreen().availableGeometry()
                dock.move(rect.topLeft() + QPoint(30, 30))
            dock.show()

    def save_layout(self):
        try:
            self.store.write("layouts", self.layout_name.text(), self.layout_data())
            self.refresh_saved_menus(); self.layout_menu.setCurrentText(self.layout_name.text().strip())
        except Exception as exc: self.show_error(str(exc))

    def recall_layout(self):
        try: self.apply_layout(self.store.read("layouts", self.layout_menu.currentText()))
        except Exception as exc: self.show_error(str(exc))

    def restore_session_layout(self):
        path = self.store.directory / "session-layout.json"
        if path.exists():
            import json
            try: self.apply_layout(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc: self.show_error(str(exc))

    def closeEvent(self, event):
        self.stop()
        if self.worker and self.worker.isRunning() and not self.worker.wait(5000):
            self.show_error("Waiting for camera capture to return; Stop and close again.")
            event.ignore(); return
        self.timer.stop()
        self.frame_timer.stop()
        import json
        self.store.directory.mkdir(parents=True, exist_ok=True)
        (self.store.directory / "session-layout.json").write_text(json.dumps(self.layout_data()), encoding="utf-8")
        self.bridge.close()
        for dock in self.docks.values(): dock.close()
        event.accept()


def run(camera_index=0, model_path=None, mapping=None, sc_port=57121, guide_mode="simple"):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = InstrumentWindow(camera_index, model_path, mapping, bridge=Bridge(port=sc_port))
    window.settings["guide_mode"] = guide_mode
    window.sync_pitch()
    window.show()
    app.exec()
