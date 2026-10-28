"""English, dockable production UI for the existing instrument pipeline."""
from copy import deepcopy
import base64
import sys
import time
import threading

from PySide6.QtCore import Qt, QTimer, QByteArray, QRect, QPoint, QEvent, QUrl
from PySide6.QtGui import QAction, QKeySequence, QFont, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QLabel, QComboBox, QDoubleSpinBox, QLineEdit,
    QMessageBox, QSizePolicy, QLayout, QMenu, QToolButton, QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDialog, QPlainTextEdit,
)

from src.pitch import NOTE_NAMES, SCALE_NAMES, PITCH_GUIDE_MODE_NAMES, midi_to_freq, freq_to_midi, format_midi_note
from src.mapping import build_articulation_runtime_config
from .catalog import CATALOG, GROUPS, Parameter, ROOT
from .state import initial_settings, validate_settings, Store
from .transport import Bridge
from .camera import CameraWorker
from .performance import PerformanceRecorder
from .effects import FX_SPECS, LEGACY_FX, validate_effects, sync_legacy_values
from .effects_panel import EffectsPanel
from .panels import PanelDock, Disclosure, AdaptiveSettings
from .audio_setup import MachineAudio, AudioSetup, available
from .keys import EffectKeys
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
QWidget#panelTitle { background:#2d3637; }
QLabel#panelHeading { font-weight:600; }
QToolButton { padding:4px; color:#e5ece9; }
QPushButton:focus, QComboBox:focus, QDoubleSpinBox:focus, QToolButton:focus { border:1px solid #90bdeb; }
QTableWidget { background:#182020; gridline-color:#344342; }
QHeaderView::section { background:#2d3637; padding:5px; border:0; }
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
        self.tiles = []
        self.pairs = []
        self.build()

    def build(self):
        for module in self.modules: module.hide()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.modules, self.refs, self.plots = [], {}, []
        self.tiles = []
        self.pairs = []
        probe = self.window.settings["probe"]
        values = self.window.settings["probes"][probe]
        for title, keys in GROUPS[probe]:
            if probe == "basic" and title in ("Delay", "Reverb"):
                continue  # These controls now live in the common Effects panel.
            plot = None
            prefix = {"Filter Env": "filterEnv", "Articulation": "articulation", "Performance / Output": "performance"}.get(title)
            if prefix:
                plot = EnvelopePlot(prefix, values)
                self.plots.append(plot)
            headers = {"Additive": "additiveOn", "Osc 2": "osc2On", "Performance / Output": "performanceGate",
                       "Articulation": "articulationOn", "Filter": "filterOn", "Filter Env": "filterEnvOn",
                       "Hand Tone": "handToneOn", "Monitor": "monitorOn", "Portamento": "portamentoOn", "Soft Clip": "softClipOn"}
            module = Module(title, [CATALOG[probe][k] for k in keys.split()], values, self.window.parameter_changed,
                            title == "Harmonics", plot, header_keys={headers.get(title)})
            self.modules.append(module)
            self.refs.update(module.controls)
        pending_osc = []
        by_title = {module.title: module for module in self.modules}
        for module in self.modules:
            if module.title in ("Osc 1", "Osc 2"):
                pending_osc.append(module)
                if len(pending_osc) == 2:
                    pair = QWidget(); pair_layout = QHBoxLayout(pair)
                    pair_layout.setContentsMargins(0,0,0,0)
                    for osc in pending_osc: pair_layout.addWidget(osc,1,Qt.AlignmentFlag.AlignTop)
                    self.tiles.append((self.wide_section(pair, "Osc 1 / Osc 2 • widen or detach Controls to compare"), True))
            elif module.title == "Harmonics":
                self.tiles.append((self.wide_section(module, "Harmonics 1–12 • widen or detach Controls for all faders"), True))
            elif probe == "subtractive" and module.title == "Filter":
                pair = QWidget(); grid = QGridLayout(pair); grid.setContentsMargins(0,0,0,0)
                self.pairs.append((grid, module, by_title["Filter Env"]))
                self.tiles.append((pair, True))
            elif probe == "subtractive" and module.title == "Filter Env":
                continue
            else: self.tiles.append((module, module.title == "Additive"))
        self.columns = 0
        self.reflow()

    def wide_section(self, widget, hint):
        # Confine unavoidable minimum width to this section, not all Controls.
        frame = QWidget(); layout = QVBoxLayout(frame); layout.setContentsMargins(0,0,0,0)
        note = QLabel(hint); note.setWordWrap(True); layout.addWidget(note)
        area = scroll(widget); area.setMinimumWidth(0)
        area.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        area.setFixedHeight(widget.minimumSizeHint().height() + 24)
        note.hide()
        area.horizontalScrollBar().rangeChanged.connect(lambda minimum, maximum: note.setVisible(maximum > 0))
        layout.addWidget(area)
        return frame

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self, available_width=None):
        columns = max(1, min(3, (self.width() if available_width is None else available_width) // 380))
        if columns == self.columns:
            return
        self.columns = columns
        for grid, left, right in self.pairs:
            grid.removeWidget(left); grid.removeWidget(right)
            grid.addWidget(left,0,0,Qt.AlignmentFlag.AlignTop)
            grid.addWidget(right,0 if columns > 1 else 1,1 if columns > 1 else 0,Qt.AlignmentFlag.AlignTop)
            grid.setColumnStretch(0,1); grid.setColumnStretch(1,1 if columns > 1 else 0)
        while self.grid.count():
            self.grid.takeAt(0)
        row, col = 0, 0
        for module, full_width in self.tiles:
            if full_width:
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
        self.setWindowTitle("Handtracking Theremin • Regular")
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
        self.metrics = PerformanceRecorder()
        self.performance_print = False
        self.performance_interval = 1.
        self.performance_at = 0
        self.audio_dialog = None
        self.audio_prompted = False
        self.audio_generation = None
        self.last_audio_state = None
        self.machine_audio = MachineAudio(self.store.directory)
        self.audio_config = None
        self.thru_on, self.thru_level = False, 1.
        self.audio_load_error = None
        self.error_history = []
        self.status_dialog = None
        try:
            self.audio_config = self.machine_audio.load()
            self.thru_level = self.machine_audio.thru_level()
        except Exception as exc: self.audio_load_error = str(exc)
        self.effect_keys = EffectKeys(self)
        self.patch_baseline = deepcopy(validate_settings(self.settings))
        self.layout_baseline = None
        self.setDockOptions(QMainWindow.DockOption.AllowNestedDocks | QMainWindow.DockOption.AnimatedDocks)
        central = QWidget()
        central.setMaximumSize(0, 0)
        self.setCentralWidget(central)
        self.make_menu()
        self.docks = {}
        camera = self.make_camera()
        controls = self.make_controls()
        analysis = self.make_analysis()
        self.effects_panel = EffectsPanel(self)
        self.effects_panel.thru_level.setValue(self.thru_level)
        for name, content in (("Camera", camera), ("Controls", controls), ("Analysis", analysis), ("Effects", self.effects_panel)):
            dock = PanelDock(name, self, content)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea if name in ("Controls", "Effects") else Qt.DockWidgetArea.LeftDockWidgetArea, dock)
            self.docks[name] = dock
        self.splitDockWidget(self.docks["Camera"], self.docks["Analysis"], Qt.Orientation.Vertical)
        self.splitDockWidget(self.docks["Controls"], self.docks["Effects"], Qt.Orientation.Vertical)
        self.resizeDocks([self.docks["Camera"], self.docks["Controls"]], [690, 810], Qt.Orientation.Horizontal)
        self.resizeDocks([self.docks["Camera"], self.docks["Analysis"]], [570, 290], Qt.Orientation.Vertical)
        self.bridge.state.connect(self.receive_state)
        self.bridge.telemetry.connect(self.receive_monitor)
        self.bridge.error.connect(self.show_error)
        if hasattr(self.bridge, "audio_changed"):
            self.bridge.audio_changed.connect(self.receive_audio)
            self.bridge.devices_changed.connect(self.receive_devices)
            self.bridge.fx_state.connect(self.receive_fx_state)
            self.bridge.order_changed.connect(self.receive_fx_order)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.consume_frame)
        self.frame_timer.start(33)
        self.restore_session_layout()
        self.layout_baseline = self.layout_data()
        if self.audio_load_error: self.show_error(self.audio_load_error)

    def make_menu(self):
        bar = QWidget(); outer = QVBoxLayout(bar); outer.setContentsMargins(6,4,6,4); outer.setSpacing(3)
        self.patch_name = QLineEdit(self); self.patch_name.hide()
        self.layout_name = QLineEdit(self); self.layout_name.hide()
        self.patch_current = QLabel("Untitled"); self.layout_current = QLabel("Untitled")
        for current in (self.patch_current,self.layout_current):
            current.setMaximumWidth(150)
            current.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
            current.setMinimumWidth(65)
        self.patch_menu = QComboBox(); self.layout_menu = QComboBox()
        saved = QHBoxLayout()
        self.patch_dirty = QLabel(); self.layout_dirty = QLabel()
        for category, combo, dirty in (("Patch",self.patch_menu,self.patch_dirty),("Layout",self.layout_menu,self.layout_dirty)):
            combo.setMinimumWidth(90); combo.setMaximumWidth(180)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(10)
            saved.addWidget(QLabel(category)); saved.addWidget(self.patch_current if category == "Patch" else self.layout_current); saved.addWidget(dirty)
            save=QToolButton(); save.setText("Save"); save.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            save.clicked.connect(lambda checked=False,c=category:self.save_named(c))
            menu=QMenu(save); menu.addAction("Save As…",lambda c=category:self.save_named(c,True)); save.setMenu(menu)
            saved.addWidget(save)
            saved.addWidget(combo,1)
            saved.addWidget(button("Recall",self.recall_patch if category=="Patch" else self.recall_layout))
        saved.addStretch(); outer.addLayout(saved)
        row = QHBoxLayout()
        row.addWidget(self.transport_bar(local=False))
        self.system_status = QLabel("SC language: disconnected · Audio: not ready · Camera: stopped")
        self.system_status.setWordWrap(True); row.addWidget(self.system_status,1)
        panels = QToolButton(); panels.setText("Panels"); panels.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(panels); menu.aboutToShow.connect(lambda:self.populate_panels(menu)); panels.setMenu(menu)
        row.addWidget(panels); row.addWidget(button("Audio Setup",self.open_audio_setup))
        outer.addLayout(row); self.setMenuWidget(bar)
        self.error_banner = button("", self.open_status)
        self.error_banner.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.error_banner.setObjectName("panic"); self.error_banner.hide(); outer.addWidget(self.error_banner)
        self.refresh_saved_menus()
        for name, shortcut, callback in (("Start", "F5", self.start), ("Stop", "F6", self.stop), ("PANIC", "F12", self.panic)):
            action = QAction(name, self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            action.triggered.connect(callback)
            self.addAction(action)

    def transport_bar(self, local=True):
        widget = QWidget()
        if local: widget.setObjectName("localTransport")
        row = QHBoxLayout(widget); row.setContentsMargins(6, 4, 6, 4)
        for text, callback in (("Start · F5", self.start), ("Stop · F6", self.stop), ("PANIC · F12", self.panic)):
            b = button(text, callback)
            if text.startswith("PANIC"):
                b.setObjectName("panic")
            row.addWidget(b)
        row.addStretch()
        if local:
            status = button("Status / Log", self.open_status)
            row.addWidget(status)
        return widget

    def populate_panels(self, menu):
        menu.clear()
        for name,dock in self.docks.items():
            submenu=menu.addMenu(name)
            visible=submenu.addAction("Visible"); visible.setCheckable(True); visible.setChecked(not dock.isHidden())
            visible.toggled.connect(dock.setVisible)
            submenu.addAction("Bring to Front",dock.bring_forward)
        menu.addSeparator(); menu.addAction("Recover Windows",self.recover_windows)

    def recover_windows(self):
        for dock in self.docks.values(): dock.recover(force=True)

    def save_named(self, category, save_as=False):
        combo,field=(self.patch_menu,self.patch_name) if category=="Patch" else (self.layout_menu,self.layout_name)
        name=field.text()
        if save_as or not name:
            dialog=QInputDialog(self); dialog.setWindowTitle("Save " + category)
            dialog.setLabelText(category + " name"); dialog.setTextValue(name)
            dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,any(d.isFloating() and d.pinned for d in self.docks.values()))
            if not dialog.exec(): return
            name=dialog.textValue().strip()
            if not name: return
        field.setText(name)
        (self.save_patch if category=="Patch" else self.save_layout)()

    def update_pitch_summary(self):
        m=self.settings["mapping"]
        self.pitch_summary.setText(f"{m['pitch_root']} · {m['pitch_scale']} · {m['pitch_min_freq']:.2f}–{m['pitch_max_freq']:.2f} Hz · Quantize {'ON' if m['quantize_pitch'] else 'OFF'}")

    def update_system_status(self):
        connected=self.bridge.connected
        audio=getattr(self.bridge,"audio_status",{}).get("state","ready") if connected else "disconnected"
        camera="error" if self.camera_error else "stopping" if self.camera_stopping else "running" if self.worker and self.worker.isRunning() else "waiting" if self.start_requested else "stopped"
        self.system_status.setText(f"SC language: {'connected' if connected else 'disconnected'} · Audio: {audio} · Camera: {camera}")
        self.system_status.setStyleSheet("color:#e8ac81" if self.camera_error or audio in ("failed","missing-device") else "color:#90cfb8" if connected and audio == "ready" else "color:#e5ece9")
        channels=getattr(self.bridge,'audio_status',{}).get('input_channels',0)
        self.effects_panel.thru_status.setText(f"Input: {channels} channels" if connected and audio == "ready" else "Input: not ready")
        self.effects_panel.thru.setToolTip(f"Dry stereo input: {getattr(self.bridge,'audio_status',{}).get('input_channels',0)} channels • outside the FX chain")
        self.patch_dirty.setText("*" if validate_settings(self.settings)!=self.patch_baseline else "")
        self.patch_dirty.setToolTip("Patch has unsaved changes")
        if self.layout_baseline is not None:
            self.layout_dirty.setText("*" if self.layout_data()!=self.layout_baseline else "")
            self.layout_dirty.setToolTip("Layout has unsaved changes")

    def update_monitor_table(self, values):
        actual_pitch=values.get("oscFreq",values.get("followedFreq"))
        effective=values.get("effectiveCutoff",values.get("filterFreq"))
        manual=self.settings["probes"][self.settings["probe"]]["filterCutoff"]
        for row,(name,value,source) in enumerate((("Pitch",actual_pitch,"Measured"),("Manual Cutoff",manual,"Setting"),("Effective Cutoff",effective,"Measured"))):
            self.primary_values.item(row,0).setText(name)
            self.primary_values.item(row,1).setText("—" if value is None else f"{value:.3f} Hz")
            self.primary_values.item(row,2).setText("No data" if value is None else source)
        primary=("oscFreq","followedFreq","effectiveCutoff","filterFreq")
        rows=sorted(values.items(),key=lambda item:(primary.index(item[0]) if item[0] in primary else len(primary),item[0]))
        self.monitor_table.setVisible(bool(rows))
        self.monitor_table.setRowCount(len(rows))
        for row,(key,value) in enumerate(rows):
            unit=" Hz" if "freq" in key.lower() or "cutoff" in key.lower() else ""
            for column,text in enumerate((key,f"{value:.3f}{unit}")):
                item=self.monitor_table.item(row,column)
                if item is None: item=QTableWidgetItem(); self.monitor_table.setItem(row,column,item)
                item.setText(text)
                if column: item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def make_camera(self):
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.transport_bar())
        self.camera_status = QLabel("Camera stopped"); self.camera_status.setWordWrap(True)
        toggle_row = QHBoxLayout()
        toggle_row.addWidget(self.camera_status, 1)
        self.camera_settings_toggle = button("Settings", lambda: self.camera_settings_area.setVisible(self.camera_settings_toggle.isChecked()))
        self.camera_settings_toggle.setCheckable(True); self.camera_settings_toggle.setChecked(True)
        toggle_row.addWidget(self.camera_settings_toggle)
        layout.addLayout(toggle_row)
        self.camera_view = CameraView(self.settings); layout.addWidget(self.camera_view, 1)
        self.camera_view.metrics = self.metrics
        settings = AdaptiveSettings(self.reflow_camera_settings); columns = QHBoxLayout(settings)
        columns.setContentsMargins(8,4,8,4); columns.setSpacing(12)
        self.camera_compact = None
        self.mapping_labels = {}
        self.pitch_labels = {}
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
            wrapper=QWidget(); box=QVBoxLayout(wrapper); box.setContentsMargins(0,0,0,0); box.setSpacing(3)
            caption=QLabel(title); caption.hide(); box.addWidget(caption); box.addWidget(control)
            self.mapping_labels[key]=caption
            ll.addWidget(wrapper); self.mapping_refs[key] = control
        ll.addStretch()
        right = QWidget(); rl = QGridLayout(right); rl.setContentsMargins(0, 0, 0, 0)
        rl.setAlignment(Qt.AlignmentFlag.AlignTop)
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
            caption=QLabel(key); self.pitch_labels[key]=caption
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
            rl.addWidget(caption, row, 0); rl.addWidget(combo, row, 1, 1, 2)
            self.pitch_refs[key] = combo
        for row, side in enumerate(("Min", "Max"), 5):
            note = QComboBox(); note.addItems([format_midi_note(i) for i in range(128)])
            hz = QDoubleSpinBox(); hz.setRange(midi_to_freq(0), midi_to_freq(127)); hz.setDecimals(5); hz.setSingleStep(.001); hz.setSuffix(" Hz"); hz.setKeyboardTracking(False)
            freq = mapping[f"pitch_{side.lower()}_freq"]
            hz.setValue(freq); note.setCurrentIndex(round(freq_to_midi(freq)))
            note.currentIndexChanged.connect(lambda value, side=side: self.range_changed(side, midi_to_freq(value)))
            hz.valueChanged.connect(lambda value, side=side: self.range_changed(side, value))
            caption=QLabel(side); self.pitch_labels[side]=caption
            rl.addWidget(caption, row, 0); rl.addWidget(note, row, 1); rl.addWidget(hz, row, 2)
            self.pitch_refs[side] = (note, hz)
        columns.addWidget(left, 1); columns.addWidget(right, 1)
        columns.setAlignment(Qt.AlignmentFlag.AlignTop)
        settings.setMinimumWidth(0)
        self.camera_settings_content = settings
        self.camera_settings_columns = columns
        self.camera_left_layout, self.camera_right_layout = ll, rl
        settings_area = scroll(settings); settings_area.setMinimumHeight(120); settings_area.setMaximumHeight(240)
        settings_area.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(settings_area)
        self.camera_settings_area = settings_area
        settings_area.viewport().installEventFilter(self)
        self.pitch_summary = QLabel(); self.pitch_summary.setWordWrap(True)
        layout.addWidget(self.pitch_summary)
        self.update_pitch_summary()
        self.camera_settings_toggle.setChecked(False); settings_area.hide()
        return panel

    def eventFilter(self, obj, event):
        if hasattr(self, "camera_settings_area") and obj is self.camera_settings_area.viewport() and event.type() == QEvent.Type.Resize:
            self.reflow_camera_settings(event.size().width() < 650)
        if hasattr(self, "controls_area") and obj is self.controls_area.viewport() and event.type() == QEvent.Type.Resize:
            self.controls.reflow(event.size().width())
        return super().eventFilter(obj, event)

    def reflow_camera_settings(self, compact):
        if not hasattr(self,"camera_right_layout") or compact == self.camera_compact: return
        self.camera_compact=compact
        for key, control in self.mapping_refs.items():
            control.findChild(QLabel).setVisible(not compact)
            self.mapping_labels[key].setVisible(compact)
        grid=self.camera_right_layout
        for i,key in enumerate(("Root","Scale","Guide Mode","Quantize")):
            caption,combo=self.pitch_labels[key],self.pitch_refs[key]
            grid.removeWidget(caption); grid.removeWidget(combo)
            if compact:
                grid.addWidget(caption,1+i*2,0,1,3); grid.addWidget(combo,2+i*2,0,1,3)
            else:
                grid.addWidget(caption,1+i,0); grid.addWidget(combo,1+i,1,1,2)
        for i,side in enumerate(("Min","Max")):
            caption=self.pitch_labels[side]; note,hz=self.pitch_refs[side]
            for control in (caption,note,hz): grid.removeWidget(control)
            if compact:
                grid.addWidget(caption,9+i*2,0); grid.addWidget(note,9+i*2,1,1,2); grid.addWidget(hz,10+i*2,0,1,3)
            else:
                grid.addWidget(caption,5+i,0); grid.addWidget(note,5+i,1); grid.addWidget(hz,5+i,2)

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
        self.connection = QLabel("SC disconnected • settings are local"); self.connection.setWordWrap(True); self.connection.hide(); layout.addWidget(self.connection)
        self.controls = ControlsArea(self)
        self.controls_area = scroll(self.controls); layout.addWidget(self.controls_area, 1)
        self.controls_area.viewport().installEventFilter(self)
        self.set_path_label()
        return panel

    def make_analysis(self):
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.transport_bar())
        content = QWidget(); body = QVBoxLayout(content)
        self.filter_plot = FilterPlot(self.settings); body.addWidget(self.filter_plot)
        self.primary_values = QTableWidget(3,3)
        self.primary_values.horizontalHeader().hide(); self.primary_values.verticalHeader().hide()
        self.primary_values.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.primary_values.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for column in (1,2): self.primary_values.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.ResizeToContents)
        self.primary_values.setFixedHeight(94)
        for row in range(3):
            for column in range(3):
                item=QTableWidgetItem(); self.primary_values.setItem(row,column,item)
                if column == 1: item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        body.addWidget(self.primary_values)
        self.monitor_label = QLabel("SC monitor • not received"); self.monitor_label.setWordWrap(True); body.addWidget(self.monitor_label)
        self.monitor_table = QTableWidget(0,2)
        self.monitor_table.setHorizontalHeaderLabels(["SC parameter", "Measured value"])
        self.monitor_table.verticalHeader().hide()
        self.monitor_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.monitor_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.monitor_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.monitor_table.setMinimumHeight(155); self.monitor_table.setMaximumHeight(230)
        diagnostics = QWidget(); diagnostics_body = QVBoxLayout(diagnostics); diagnostics_body.setContentsMargins(0,0,0,0)
        diagnostics_body.addWidget(self.monitor_table)
        self.performance_label = QLabel("Software timing • no camera samples. This is not hand-to-sound latency.")
        self.performance_label.setWordWrap(True); diagnostics_body.addWidget(self.performance_label)
        diagnostics_body.addWidget(button("Save Timing Log", self.save_timing))
        self.diagnostics = Disclosure("SC telemetry / Timing diagnostics",diagnostics); body.addWidget(self.diagnostics)
        scopes = QHBoxLayout()
        scopes.addWidget(button("Open Scope (SC signal)", lambda: self.open_scope("scope")))
        scopes.addWidget(button("Open FreqScope (SC signal)", lambda: self.open_scope("spectrum")))
        body.addLayout(scopes)
        note = QLabel("Scope / FreqScope open separate SC signal windows; panel pins do not apply to them. Filter and envelope curves are models.")
        note.setWordWrap(True); body.addWidget(note)
        layout.addWidget(scroll(content), 1)
        self.update_monitor_table({})
        return panel

    def set_path_label(self):
        self.path_label.setText({
            "basic": "Base sine + additive → Soft Clip → Filter → Performance Gate → Shared Effects → Output",
            "subtractive": "Oscillators / Sub / Noise → RLPF → Pinch Amp → Articulation → Performance Gate → Shared Effects → Output",
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
        if key in LEGACY_FX and self.settings["probe"] == "basic":
            self.effect_changed(*LEGACY_FX[key], value)
            return
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
            if not self.bridge.connected or not getattr(self.bridge, "audio_ready", True):
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
        self.update_pitch_summary()
        self.camera_view.update(); self.filter_plot.update()

    def select_probe(self, index):
        self.panic()
        self.settings["probe"] = ("basic", "subtractive")[index]
        self.probe_menu.blockSignals(True); self.probe_menu.setCurrentIndex(index); self.probe_menu.blockSignals(False)
        self.monitor, self.monitor_at = {}, 0
        self.controls.build(); self.set_path_label()
        self.synced = False
        if self.bridge.connected and getattr(self.bridge, "audio_ready", True):
            self.sync_backend()

    def sync_backend(self):
        self.bridge.request("select", self.settings["probe"])
        for probe, values in self.settings["probes"].items():
            values["performanceGate"] = 0
            pairs = [item for key, value in values.items() if key != "performanceGate" for item in (key, value)]
            self.bridge.request("restore", probe, *pairs)
        for effect, values in self.settings["effects"]["values"].items():
            for key, value in values.items(): self.bridge.request("fx", effect, key, value)
        for effect in self.settings["effects"]["mappings"]: self.send_mapping_source(effect)
        self.bridge.request("order", *self.settings["effects"]["order"])
        self.bridge.request("thru", int(self.thru_on), self.thru_level)
        self.synced = True

    def effect_changed(self, effect, key, value):
        value = FX_SPECS[effect][key].validate(value)
        self.settings["effects"]["values"][effect][key] = value
        sync_legacy_values(self.settings)
        if self.bridge.connected and getattr(self.bridge, "audio_ready", True): self.bridge.request("fx", effect, key, value)
        self.configure_worker_effects()
        if hasattr(self, "effects_panel"): self.effects_panel.modules[effect].refresh()

    def send_mapping_source(self, effect):
        mapping = self.settings["effects"]["mappings"][effect]
        self.bridge.request("mod_source", effect, mapping["target"], int(mapping["source"] != "manual"))

    def effect_mapping_changed(self, effect, key, value):
        candidate = deepcopy(self.settings["effects"])
        candidate["mappings"][effect][key] = value
        try:
            candidate = validate_effects(candidate)
            self.settings["effects"] = candidate
            if self.bridge.connected and getattr(self.bridge, "audio_ready", True): self.send_mapping_source(effect)
            self.configure_worker_effects()
        except Exception as exc: self.show_error(str(exc))
        self.effects_panel.modules[effect].refresh()

    def effect_order_changed(self, order):
        candidate = deepcopy(self.settings["effects"]); candidate["order"] = order
        try:
            candidate = validate_effects(candidate)
            self.settings["effects"]["order"] = candidate["order"]
            if self.bridge.connected and getattr(self.bridge, "audio_ready", True): self.bridge.request("order", *order)
        except Exception as exc: self.show_error(str(exc))

    def configure_worker_effects(self):
        if self.worker and hasattr(self.worker, "configure_effects"):
            self.worker.configure_effects(self.settings["effects"], getattr(self.bridge, "send_modulation", None))

    def receive_fx_state(self, values):
        if self.bridge.busy or not self.synced: return
        changed = False
        for path, value in values.items():
            try:
                effect, key = path.split(".")
                value = FX_SPECS[effect][key].validate(value)
                if self.settings["effects"]["values"][effect][key] != value:
                    self.settings["effects"]["values"][effect][key] = value
                    changed = True
            except (KeyError, ValueError): continue
        if changed:
            sync_legacy_values(self.settings)
            self.effects_panel.refresh(); self.configure_worker_effects()

    def receive_fx_order(self, order):
        if self.bridge.busy or not self.synced: return
        if order == self.settings["effects"]["order"]: return
        candidate = deepcopy(self.settings["effects"]); candidate["order"] = order
        try: self.settings["effects"]["order"] = validate_effects(candidate)["order"]
        except ValueError: return
        self.effects_panel.refresh()

    def toggle_thru(self):
        enabled = not self.thru_on
        if enabled and (not getattr(self.bridge, "audio_ready", False) or self.bridge.audio_status.get("input_channels", 0) < 2):
            self.show_error("Stereo input is unavailable. Select an input in Audio Setup and restart SC.")
            self.effects_panel.refresh(); return
        self.thru_on = enabled
        self.bridge.request("thru", int(enabled), self.thru_level)
        self.effects_panel.refresh()

    def set_thru_level(self, value):
        self.thru_level = value
        try: self.machine_audio.save_thru_level(value)
        except Exception as exc: self.show_error(str(exc))
        if self.bridge.connected: self.bridge.request("thru", int(self.thru_on), value)

    def open_audio_setup(self):
        if not hasattr(self.bridge, "devices"): return False
        if not self.bridge.connected and not self.launch_sc(): return False
        self.bridge.request("devices")
        if self.audio_dialog is None: self.audio_dialog = AudioSetup(self)
        self.audio_dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, any(d.isFloating() and d.pinned for d in self.docks.values()))
        self.audio_dialog.populate(); self.audio_dialog.show(); self.audio_dialog.raise_(); self.audio_dialog.activateWindow()
        return True

    def require_audio_setup(self):
        # Waiting for a human to choose devices is not an SC startup timeout.
        # Cancel Start so Apply/recovery can never start the camera or Gate.
        self.panic()
        self.audio_prompted = True
        self.camera_status.setText("Audio Setup required • select devices and Apply / Restart SC, then press Start")
        if not self.open_audio_setup():
            self.camera_status.setText("SC launch failed • see status message")

    def receive_devices(self):
        if self.audio_dialog is not None: self.audio_dialog.populate(self.audio_dialog.current())
        if not self.bridge.devices_received or self.bridge.audio_requested: return
        if self.audio_config is not None and available(self.audio_config, self.bridge.devices) and not self.audio_load_error:
            self.bridge.configure_audio(self.audio_config)
        elif not self.audio_prompted:
            self.audio_prompted = True
            self.require_audio_setup()

    def receive_audio(self, status):
        state = status["state"]
        changed = state != self.last_audio_state or status["generation"] != self.audio_generation
        self.last_audio_state = state
        if status["generation"] != self.audio_generation:
            self.audio_generation = status["generation"]
            self.synced = False
        if changed and state in ("booting", "failed", "missing-device"):
            self.synced = False
            self.monitor, self.monitor_at = {}, 0
            if self.worker or state != "booting": self.stop()
            self.thru_on = False
            self.effects_panel.refresh()
            if state != "booting":
                self.camera_status.setText("Audio unavailable • open Audio Setup")
                self.show_error(status["error"])
        if self.audio_dialog is not None:
            self.audio_dialog.explain()
            if status["error"]: self.audio_dialog.status.setText(status["error"])
            elif state == "ready": self.audio_dialog.status.setText("Audio ready. Gate and Thru are off; press Start explicitly to resume.")

    def save_timing(self):
        path = ROOT / "logs" / ("ui-timing-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
        self.metrics.save(path, audio=getattr(self.bridge, "audio_status", {}))
        self.statusBar().showMessage("Timing log saved: " + str(path), 12000)

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
        status = getattr(self.bridge, "audio_status", {})
        if not getattr(self.bridge, "audio_ready", True) and hasattr(self.bridge, "devices"):
            needs_selection = not getattr(self.bridge, "audio_requested", False) and (
                self.audio_config is None or self.audio_load_error or (
                    self.bridge.devices_received and not available(self.audio_config, self.bridge.devices)))
            if needs_selection or status.get("state") in ("failed", "missing-device"):
                self.require_audio_setup()
                return
        if not self.bridge.connected or not getattr(self.bridge, "audio_ready", True) or not self.synced or self.bridge.busy:
            if not self.start_requested:
                self.start_requested_at = time.monotonic()
            self.start_requested = True
            self.camera_error = None
            self.camera_status.setText("Start pending • " + self.startup_stage())
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
        self.worker.metrics = self.metrics
        self.configure_worker_effects()
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
            if self.latest_frame is not None:
                self.metrics.overwrite()
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

    def startup_stage(self):
        if not self.bridge.connected: return "waiting for SC language connection"
        if not getattr(self.bridge, "audio_ready", True): return "waiting for audio server boot"
        return "synchronizing SC settings"

    def startup_timeout(self):
        stage = self.startup_stage()
        audio = getattr(self.bridge, "audio_status", {})
        queued = list(getattr(self.bridge, "queue", []))
        operation = queued[0][1] if queued else "none"
        log_path = getattr(self.bridge, "log_path", ROOT / "logs" / "regular-sc.log")
        detail = (f"SC startup timed out: {stage}; audio={audio.get('state', 'unknown')}; "
                  f"pending={operation}; log={log_path}")
        if audio.get("error"): detail += "; " + audio["error"]
        print("[regular-startup] " + detail, flush=True)
        self.panic()
        self.camera_status.setText("SC startup timed out • " + stage + " • open Audio Setup / SC Log")
        self.camera_status.setToolTip(detail)
        self.show_error(detail)

    def tick(self):
        self.bridge.tick()
        connected = self.bridge.connected
        if connected and not self.last_connected:
            requested, requested_at = self.start_requested, self.start_requested_at
            if getattr(self.bridge, "audio_ready", True):
                self.panic()
            else:
                # The new language session is already muted. Keep a queued
                # device configuration instead of losing it during handshake.
                for values in self.settings["probes"].values(): values["performanceGate"] = 0
            self.synced = False
            self.start_requested, self.start_requested_at = requested, requested_at
            if requested:
                self.camera_status.setText("Start pending • synchronizing SC")
        if connected and getattr(self.bridge, "audio_ready", True) and not self.synced:
            self.sync_backend()
        if not connected and self.last_connected:
            self.panic(); self.synced = False
        self.last_connected = connected
        if self.start_requested:
            if time.monotonic() - self.start_requested_at > 45:
                self.startup_timeout()
            elif connected and getattr(self.bridge, "audio_ready", True) and self.synced and not self.bridge.busy:
                self.start()
            else:
                self.camera_status.setText("Start pending • " + self.startup_stage())
        camera_state = "camera running" if self.worker and self.worker.isRunning() else "camera stopped"
        self.connection.setText("SC connected • synchronizing" if connected and self.bridge.busy else "SC connected • " + camera_state if connected else "SC disconnected • settings are local")
        if connected and not getattr(self.bridge, "audio_ready", True):
            self.connection.setText("SC language connected • Audio " + self.bridge.audio_status.get("state", "unconfigured"))
        values = self.settings["probes"][self.settings["probe"]]
        fresh_seconds = max(1, 3 / max(.1, values["monitorRate"]))
        fresh = connected and getattr(self.bridge, "audio_ready", True) and self.synced and values["monitorOn"] and time.monotonic() - self.monitor_at < fresh_seconds
        self.filter_plot.fresh_seconds = fresh_seconds
        self.filter_plot.monitor = self.monitor if fresh else {}
        self.filter_plot.received = self.monitor_at if fresh else 0
        if self.filter_plot.isVisible(): self.filter_plot.update()
        if fresh:
            self.monitor_label.setText("SC monitor • measured")
            self.update_monitor_table(self.monitor)
        else:
            self.update_monitor_table({})
            self.monitor_label.setText("SC monitor • not received" if connected else "SC disconnected • no measurements")
            if not connected:
                for key, control in self.controls.refs.items():
                    if CATALOG[self.settings["probe"]][key].kind == "readout":
                        control.show_value(None)
        if time.monotonic() - self.performance_at >= self.performance_interval:
            self.performance_at = time.monotonic()
            self.update_system_status()
            self.refresh_status_dialog()
            summary = self.metrics.summary(recent=300)
            timings = summary["timings_ms"]
            fmt = lambda key: f"{timings[key]['median']:.1f} / {timings[key]['p95']:.1f} / {timings[key]['max']:.1f} ms" if timings.get(key) else "not received"
            self.performance_label.setText(f"Software timing • {summary['fps']:.1f} FPS • median / p95 / max\nRead → OSC: {fmt('read_to_osc_ms')}\nRead → GUI paint: {fmt('display_age_ms')}\nDisplay queue: 1 • superseded: {summary['display_frames_superseded']} • sensor / DAC / acoustic latency unknown")
            if self.performance_print:
                import json
                print("[regular-perf] " + json.dumps(summary), flush=True)

    def show_error(self, message):
        self.error_history.append(str(message))
        self.error_history = self.error_history[-50:]
        self.statusBar().showMessage(message)
        self.statusBar().setToolTip(message)
        self.error_banner.setText("Attention • " + str(message).splitlines()[0][:90] + " • Status / Log")
        self.error_banner.setToolTip(str(message)); self.error_banner.show()
        self.refresh_status_dialog()

    def open_status(self):
        if self.status_dialog is None:
            self.status_dialog = QDialog(self)
            self.status_dialog.setWindowTitle("Status / Log")
            self.status_dialog.resize(620,400)
            layout=QVBoxLayout(self.status_dialog)
            self.status_detail=QLabel(); self.status_detail.setWordWrap(True); layout.addWidget(self.status_detail)
            self.error_detail=QPlainTextEdit(); self.error_detail.setReadOnly(True); layout.addWidget(self.error_detail,1)
            row=QHBoxLayout()
            row.addWidget(button("Audio Setup",self.open_audio_setup))
            row.addWidget(button("Open SC Log",self.open_sc_log))
            row.addWidget(button("Dismiss notice",self.error_banner.hide)); layout.addLayout(row)
        self.refresh_status_dialog()
        self.status_dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,any(d.isFloating() and d.pinned for d in self.docks.values()))
        self.status_dialog.show(); self.status_dialog.raise_(); self.status_dialog.activateWindow()

    def refresh_status_dialog(self):
        if self.status_dialog is None: return
        self.status_detail.setText(self.system_status.text() + "\n" + self.camera_status.text())
        self.error_detail.setPlainText("\n\n".join(self.error_history) or "No errors reported.")

    def open_sc_log(self):
        path=getattr(self.bridge,"log_path",ROOT / "logs" / "regular-sc.log")
        if not path.exists():
            self.show_error("SC log is not available yet. Launch SC from Controls or open Audio Setup.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.show_error("Could not open SC log: " + str(path))

    def refresh_saved_menus(self):
        for category, combo in (("patches", self.patch_menu), ("layouts", self.layout_menu)):
            current = combo.currentText(); combo.clear(); combo.addItems(self.store.names(category)); combo.setCurrentText(current)

    def save_patch(self):
        try:
            self.effect_keys.release_all()
            self.store.write("patches", self.patch_name.text(), validate_settings(self.settings))
            self.refresh_saved_menus(); self.patch_menu.setCurrentText(self.patch_name.text().strip())
            self.patch_baseline = deepcopy(validate_settings(self.settings))
            self.patch_current.setText(self.patch_name.text().strip())
            self.patch_current.setToolTip(self.patch_name.text().strip())
        except Exception as exc: self.show_error(str(exc))

    def recall_patch(self):
        try:
            candidate = validate_settings(self.store.read("patches", self.patch_menu.currentText()))
            self.effect_keys.release_all()
            self.panic()
            # Preserve references used by plots and the camera widget.
            self.settings.clear(); self.settings.update(candidate)
            self.patch_baseline = deepcopy(validate_settings(self.settings))
            self.patch_name.setText(self.patch_menu.currentText())
            self.patch_current.setText(self.patch_name.text())
            self.patch_current.setToolTip(self.patch_name.text())
            self.probe_menu.blockSignals(True); self.probe_menu.setCurrentIndex(("basic", "subtractive").index(candidate["probe"])); self.probe_menu.blockSignals(False)
            self.controls.build(); self.set_path_label(); self.sync_pitch(); self.sync_mapping(); self.apply_mapping()
            self.effects_panel.refresh(); self.configure_worker_effects()
            if candidate.get("migration"):
                self.statusBar().showMessage("Legacy Patch migrated: Basic Delay / Reverb moved to Effects. Original FX settings preserved in the Patch metadata.", 15000)
            self.monitor, self.monitor_at = {}, 0
            self.synced = False
            if self.bridge.connected and getattr(self.bridge, "audio_ready", True): self.sync_backend()
        except Exception as exc: self.show_error(str(exc))

    def layout_data(self):
        return {
            "geometry": bytes(self.saveGeometry().toBase64()).decode(),
            "state": bytes(self.saveState(1).toBase64()).decode(),
            "camera_settings": self.camera_settings_toggle.isChecked(),
            "panels": {name: {"pinned": dock.pinned, "locked": dock.locked, "visible": not dock.isHidden()} for name,dock in self.docks.items()},
            "effect_details": {name: module.details.toggle.isChecked() for name,module in self.effects_panel.modules.items()},
            "diagnostics": self.diagnostics.toggle.isChecked(),
            "floating": {name: list(dock.geometry().getRect()) for name, dock in self.docks.items() if dock.isFloating()},
        }

    def apply_layout(self, data):
        self.effect_keys.release_all()
        previous, baseline = self.layout_data(), self.layout_baseline
        try:
            self._apply_layout(data)
        except Exception:
            self._apply_layout(previous)
            self.layout_baseline = baseline
            raise

    def _apply_layout(self, data):
        for dock in self.docks.values(): dock.set_locked(False)
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
        for name, dock in self.docks.items():
            options = data.get("panels",{}).get(name,{})
            dock.set_pinned(options.get("pinned",False))
            dock.setVisible(options.get("visible",True))
            dock.recover()
            dock.set_locked(options.get("locked",False))
        for name,module in self.effects_panel.modules.items():
            module.details.set_expanded(data.get("effect_details",{}).get(name,False))
        self.diagnostics.set_expanded(data.get("diagnostics",False))
        self.layout_baseline = self.layout_data()

    def save_layout(self):
        try:
            self.store.write("layouts", self.layout_name.text(), self.layout_data())
            self.refresh_saved_menus(); self.layout_menu.setCurrentText(self.layout_name.text().strip())
            self.layout_baseline = self.layout_data()
            self.layout_current.setText(self.layout_name.text().strip())
            self.layout_current.setToolTip(self.layout_name.text().strip())
        except Exception as exc: self.show_error(str(exc))

    def recall_layout(self):
        try:
            self.apply_layout(self.store.read("layouts", self.layout_menu.currentText()))
            self.layout_name.setText(self.layout_menu.currentText())
            self.layout_current.setText(self.layout_name.text())
            self.layout_current.setToolTip(self.layout_name.text())
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
        self.effects_panel.timer.stop()
        self.effect_keys.close()
        if self.audio_dialog is not None: self.audio_dialog.close()
        if self.status_dialog is not None: self.status_dialog.close()
        import json
        self.store.directory.mkdir(parents=True, exist_ok=True)
        (self.store.directory / "session-layout.json").write_text(json.dumps(self.layout_data()), encoding="utf-8")
        self.bridge.close()
        for dock in self.docks.values(): dock.close()
        event.accept()


def run(camera_index=0, model_path=None, mapping=None, sc_port=57121, guide_mode="simple", show_performance_stats=False, performance_stats_interval=1.):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    from .single_instance import SingleInstance
    instance = SingleInstance(sc_port)
    if not instance.acquire():
        print("Regular UI already running; activated the existing window.", flush=True)
        return
    print("Regular UI: creating panels", flush=True)
    window = InstrumentWindow(camera_index, model_path, mapping, bridge=Bridge(port=sc_port))
    instance.attach(window)
    window.performance_print = show_performance_stats
    window.performance_interval = max(.2, performance_stats_interval)
    window.settings["guide_mode"] = guide_mode
    window.sync_pitch()
    window.show()
    print("Regular UI: ready", flush=True)
    try: app.exec()
    finally: instance.close()
