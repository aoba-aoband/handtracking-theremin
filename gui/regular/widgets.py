"""Reusable controls and explicitly labelled model/measurement views."""
import math
import time
import numpy as np

from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QSlider, QDoubleSpinBox,
    QComboBox, QPushButton, QGridLayout, QSizePolicy, QLayout,
)

from src.pitch import build_pitch_guides
from .catalog import label

GREEN = QColor("#90cfb8")
BLUE = QColor("#90bdeb")
ORANGE = QColor("#e8ac81")
MUTED = QColor("#a8bbb4")


def button(text, callback):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    return widget


class ParameterControl(QWidget):
    changed = Signal(str, float)

    def __init__(self, spec, vertical=False):
        super().__init__()
        self.spec, self.vertical = spec, vertical
        self.setToolTip(spec.key + (" • read-only (SC / tracker)" if spec.kind == "readout" else ""))
        self.setObjectName(spec.key)
        layout = QVBoxLayout(self) if vertical else QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        name = QLabel(spec.key.removeprefix("harmonic") if vertical else label(spec.key))
        if vertical:
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            name.setMinimumWidth(24 if spec.kind == "toggle" else 90)
        layout.addWidget(name)
        self.slider = self.number = self.control = None
        if spec.kind == "readout":
            self.control = QLabel("Not received")
            layout.addWidget(self.control, 1)
        elif spec.kind == "toggle":
            self.control = QPushButton("OFF")
            self.control.setCheckable(True)
            self.control.toggled.connect(lambda value: self.changed.emit(spec.key, float(value)))
            layout.addWidget(self.control)
        elif spec.kind == "choice":
            self.control = QComboBox()
            self.control.addItems(spec.choices)
            self.control.currentIndexChanged.connect(lambda value: self.changed.emit(spec.key, float(value)))
            layout.addWidget(self.control, 1)
        else:
            self.slider = QSlider(Qt.Orientation.Vertical if vertical else Qt.Orientation.Horizontal)
            self.slider.setRange(0, 10000)
            self.slider.setMinimumSize(18, 105) if vertical else self.slider.setMinimumWidth(50)
            self.number = QDoubleSpinBox()
            self.number.setRange(spec.minimum, spec.maximum)
            decimals = max(0, -int(math.floor(math.log10(spec.step)))) if spec.step else 4
            self.number.setDecimals(max(decimals, 0))
            self.number.setSingleStep(spec.step or .001)
            self.number.setKeyboardTracking(False)
            self.number.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            self.number.setMinimumWidth(58 if vertical else 78)
            self.number.setMaximumWidth(72 if vertical else 95)
            if vertical:
                layout.addWidget(self.slider, 1, Qt.AlignmentFlag.AlignHCenter)
            else:
                layout.addWidget(self.slider, 1)
            layout.addWidget(self.number)
            if not vertical:
                unit = QLabel(spec.unit)
                unit.setFixedWidth(23)
                layout.addWidget(unit)
            self.number.valueChanged.connect(lambda value: self.changed.emit(spec.key, value))
            self.slider.valueChanged.connect(self.slider_changed)
        self.show_value(spec.default)

    def slider_changed(self, position):
        s = self.spec
        norm = position / 10000
        value = s.minimum * (s.maximum / s.minimum) ** norm if s.warp == "exp" else s.minimum + (s.maximum - s.minimum) * norm
        self.changed.emit(s.key, s.validate(value))

    def show_value(self, value):
        s = self.spec
        if s.kind == "readout":
            self.control.setText("Not received" if value is None else f"{value:.3f} {s.unit}".strip())
            return
        if s.kind in ("toggle", "choice"):
            self.control.blockSignals(True)
            if s.kind == "toggle":
                self.control.setChecked(bool(value))
                self.control.setText("ON" if value else "OFF")
            else:
                self.control.setCurrentIndex(int(value))
            self.control.blockSignals(False)
        else:
            self.number.blockSignals(True)
            self.number.setValue(value)
            self.number.blockSignals(False)
            norm = math.log(max(value, s.minimum) / s.minimum) / math.log(s.maximum / s.minimum) if s.warp == "exp" else (value - s.minimum) / (s.maximum - s.minimum)
            self.slider.blockSignals(True)
            self.slider.setValue(round(norm * 10000))
            self.slider.blockSignals(False)


class Module(QWidget):
    """Self-contained section; adding modules does not change the window shell."""
    def __init__(self, title, specs, values, callback, harmonic=False, plot=None):
        super().__init__()
        self.setObjectName("module")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.controls = {}
        self.title = title
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        header = QHBoxLayout()
        heading = QLabel(title)
        heading.setFixedHeight(30)
        heading.setObjectName("heading")
        header.addWidget(heading)
        header.addStretch()
        layout.addLayout(header)
        body = QHBoxLayout() if harmonic or title == "Additive" else QVBoxLayout()
        for spec in specs:
            control = ParameterControl(spec, harmonic)
            control.changed.connect(callback)
            control.show_value(None if spec.kind == "readout" else values[spec.key])
            self.controls[spec.key] = control
            if spec.kind == "toggle" and (spec.key.endswith("On") or spec.key == "performanceGate"):
                header.addWidget(control)
            else:
                body.addWidget(control)
        layout.addLayout(body)
        if plot:
            layout.addWidget(plot)
        layout.addStretch()
        self.setMinimumWidth(780 if harmonic else 330)


class CameraView(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.image = None
        self.features, self.events = [], []
        self.fps = 0
        self.setMinimumSize(400, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setObjectName("cameraView")

    def present(self, image, features, events, fps):
        self.image, self.features, self.events, self.fps = image, features, events, fps
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#142024"))
        if self.image is None:
            p.setPen(MUTED)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Camera stopped • no frame received")
            return
        # Overlays are painted at display resolution, never scaled with pixels.
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        rect = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2, size.width(), size.height())
        p.drawImage(rect, self.image)
        m = self.settings["mapping"]
        guides = build_pitch_guides(self.settings["guide_mode"], m["pitch_min_freq"], m["pitch_max_freq"], m["pitch_root"], m["pitch_scale"])
        last_y = -100
        for guide in sorted(guides, key=lambda x: -x["pitch_norm"]):
            y = rect.top() + (1 - guide["pitch_norm"]) * rect.height()
            p.setPen(QPen(QColor("#d5ece5") if guide["is_root"] else QColor(130, 174, 163, 100), 1))
            p.drawLine(rect.left(), y, rect.right(), y)
            if y - last_y >= 22 and rect.top() + 64 < y < rect.bottom() - 38:
                text = guide["label"]
                width = p.fontMetrics().horizontalAdvance(text) + 12
                p.fillRect(QRectF(rect.right() - width - 4, y - 20, width, 20), QColor(15, 26, 28, 225))
                p.setPen(QColor("#edf5ee"))
                p.drawText(QRectF(rect.right() - width, y - 20, width - 8, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)
                last_y = y
        left = next((f for f in self.features if f.handedness.lower() == "left"), None)
        right = next((f for f in self.features if f.handedness.lower() == "right"), None)
        vals = {e.address: e.value for e in self.events}
        left_text = ["Left • detected" if left else "Left • not detected"]
        right_text = ["Right • detected" if right else "Right • not detected"]
        if left:
            left_text += [f"Pinch {left.pinch:.3f} • Gate {vals.get('/sample/left/articulation/gate', 0):.0f}", f"Tone norm {left.index_tip_x:.3f}"]
        if right:
            right_text += [f"Final {vals.get('/sample/right/pitch/final_freq', 0):.2f} Hz", f"Octave +{vals.get('/sample/right/pitch/octave_shift', 0):.0f}"]
        half = self.width() / 2
        for side, lines in enumerate((left_text, right_text)):
            area = QRectF(side * half + 8, 8, half - 16, 64)
            p.fillRect(area, QColor(15, 26, 28, 230))
            p.setPen(QColor("#edf5ee"))
            for i, text in enumerate(lines):
                p.drawText(QRectF(area.left() + 6, area.top() + i * 19, area.width() - 12, 20), Qt.AlignmentFlag.AlignVCenter, text)
        footer = f"{self.fps:.1f} FPS • {self.settings['guide_mode']} guides • Quantize {'ON' if m['quantize_pitch'] else 'OFF'}"
        p.fillRect(QRectF(8, self.height() - 28, self.width() - 16, 22), QColor(15, 26, 28, 230))
        p.drawText(QRectF(14, self.height() - 28, self.width() - 28, 22), Qt.AlignmentFlag.AlignVCenter, footer)


class EnvelopePlot(QWidget):
    def __init__(self, prefix, values):
        super().__init__()
        self.prefix, self.values = prefix, values
        self.setMinimumSize(280, 115)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#182020"))
        prefix, v = self.prefix, self.values
        if prefix == "filterEnv":
            attack, decay, sustain, release = [v[prefix + k] for k in ("Attack", "Decay", "Sustain", "Release")]
        elif prefix == "articulation":
            attack, release = v["articulationAttack"], v["articulationRelease"]
            decay, sustain = 0, 1
        else:
            attack, release = v["crescendoTime"], v["decrescendoTime"]
            decay, sustain = 0, 1
        hold = max(.1, (attack + decay + release) * .3)
        duration = max(.001, attack + decay + hold + release)
        area = QRectF(10, 30, self.width() - 20, self.height() - 54)
        path = QPainterPath()
        path.moveTo(area.left(), area.bottom())
        elapsed = 0
        for length, start, end in ((attack, 0, 1), (decay, 1, sustain), (hold, sustain, sustain), (release, sustain, 0)):
            for t in np.linspace(0, 1, 40):
                if prefix == "performance":
                    curve = 1 - math.exp(-6.907755 * t)
                else:
                    curve = (1 - math.exp(-4 * t)) / (1 - math.exp(-4))
                value = start + (end - start) * curve
                path.lineTo(area.left() + (elapsed + length * t) / duration * area.width(), area.bottom() - value * area.height())
            elapsed += length
        p.setPen(QPen(GREEN, 2))
        p.drawPath(path)
        p.setPen(MUTED)
        p.drawText(10, 18, "Timing model • normalized • not measured")
        p.drawText(10, self.height() - 7, f"0 s                                     {duration:.3f} s (illustrative hold)")


class FilterPlot(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings, self.monitor, self.received = settings, {}, 0
        self.fresh_seconds = 1
        self.setMinimumSize(400, 260)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#182020"))
        area = QRectF(48, 42, self.width() - 66, self.height() - 100)
        xmin, xmax = 8., 22000.
        x = lambda hz: area.left() + np.clip(math.log(max(xmin, hz) / xmin) / math.log(xmax / xmin), 0, 1) * area.width()
        y = lambda db: area.top() + (12 - np.clip(db, -48, 12)) / 60 * area.height()
        p.setPen(MUTED)
        for hz in (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
            p.setPen(QPen(QColor("#344342"), 1))
            p.drawLine(x(hz), area.top(), x(hz), area.bottom())
            p.setPen(MUTED)
            p.drawText(QRectF(x(hz) - 18, area.bottom() + 4, 40, 20), Qt.AlignmentFlag.AlignCenter, f"{hz // 1000}k" if hz >= 1000 else str(hz))
        for db in (12, 0, -12, -24, -36, -48):
            p.setPen(QPen(QColor("#344342"), 1))
            p.drawLine(area.left(), y(db), area.right(), y(db))
            p.setPen(MUTED)
            p.drawText(4, int(y(db) + 4), str(db))
        mapping = self.settings["mapping"]
        p.fillRect(QRectF(x(mapping["pitch_min_freq"]), area.top(), x(mapping["pitch_max_freq"]) - x(mapping["pitch_min_freq"]), area.height()), QColor(144, 207, 184, 30))
        probe = self.settings["probe"]
        values = self.settings["probes"][probe]
        manual = values["filterCutoff"]
        fresh = time.monotonic() - self.received < self.fresh_seconds
        effective = self.monitor.get("effectiveCutoff", self.monitor.get("filterFreq")) if fresh else None
        freq = self.monitor.get("followedFreq") if fresh else None
        # RLPF analogue approximation, not a measured transfer function.
        cutoff = effective if effective is not None else manual
        rq, mix = values["filterRq"], values["filterMix"] * values["filterOn"]
        path = QPainterPath()
        freqs = np.geomspace(xmin, xmax, 350)
        ratio = freqs / max(1, cutoff)
        response = 1 / (1 - ratio * ratio + 1j * rq * ratio)
        dbs = np.clip(20 * np.log10(np.maximum(1e-6, abs((1 - mix) + mix * response))), -48, 12)
        xs = area.left() + np.log(freqs / xmin) / math.log(xmax / xmin) * area.width()
        ys = area.top() + (12 - dbs) / 60 * area.height()
        for i, (xx, yy) in enumerate(zip(xs, ys)):
            path.moveTo(xx, yy) if i == 0 else path.lineTo(xx, yy)
        p.setPen(QPen(GREEN, 2)); p.drawPath(path)
        for value, color in ((manual, MUTED), (effective, ORANGE), (freq, BLUE)):
            if value is not None:
                p.setPen(QPen(color, 1, Qt.PenStyle.DashLine)); p.drawLine(x(value), area.top(), x(value), area.bottom())
        p.setPen(MUTED)
        p.drawText(8, 18, "Filter • RLPF response model (not measured) • Hz / dB")
        eff_text = f"{effective:.1f} Hz" if effective is not None else "not received"
        freq_text = f"{freq:.1f} Hz" if freq is not None else "not received"
        p.drawText(8, self.height() - 27, f"Pitch range {mapping['pitch_min_freq']:.1f}–{mapping['pitch_max_freq']:.1f} Hz • manual {manual:.1f} Hz")
        p.setPen(ORANGE); p.drawText(8, self.height() - 8, f"Effective {eff_text}    ")
        p.setPen(BLUE); p.drawText(self.width() / 2, self.height() - 8, f"Followed {freq_text}")
