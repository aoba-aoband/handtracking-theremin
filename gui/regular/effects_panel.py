"""Dockable Effects UI; previews are models, never fabricated measurements."""
from copy import deepcopy
import math
import numpy as np
from PySide6.QtCore import Qt, QTimer, QRectF, QSize, QEvent
from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor, QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QDoubleSpinBox, QCheckBox, QKeySequenceEdit, QListWidget, QListWidgetItem, QAbstractItemView, QScrollArea, QListView, QLayout)

from .effects import FX_SPECS, FX_NAMES, TARGETS, validate_effects
from .widgets import Module, button, GREEN, MUTED
from .panels import CardRack, Disclosure
from src.angle_mapping import response_curve


class EffectPlot(QWidget):
    def __init__(self, module, waveform=False):
        super().__init__(); self.module, self.waveform = module, waveform
        self.setMinimumSize(300, 105)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#182020")); p.setPen(MUTED)
        effect = self.module.effect
        settings = self.module.panel.window.settings["effects"]
        values, mapping = settings["values"][effect], settings["mappings"][effect]
        area = QRectF(12, 28, self.width()-24, self.height()-52)
        p.drawRect(area)
        x = np.linspace(0, 1, 180)
        if self.waveform:
            rate, depth = values["rate"], values["depth"]
            live = self.module.live
            if mapping["source"] != "manual" and live:
                if mapping["target"] == "rate": rate = live["value"]; depth *= live["presence"]
                else: depth = live["value"]
            phase = x * 4 * math.pi
            wave = np.sin(phase) if values["wave"] == 0 else (np.arcsin(np.sin(phase))*2/math.pi if values["wave"] == 1 else np.sign(np.sin(phase)))
            y = (1 - depth*(wave+1)/2) if effect == "tremolo" else wave*depth
            max_depth = FX_SPECS[effect]["depth"].maximum
            yplot = (1-y)/max_depth if effect == "tremolo" else .5 - y/(2*max_depth)
            title = f"LFO model • {rate:.2f} Hz / {1000/max(.05,rate):.1f} ms"
            footer = f"0 → {2000/max(.05,rate):.1f} ms • " + (f"gain {1-max_depth:g}…1" if effect == "tremolo" else f"−{max_depth:g}…+{max_depth:g} ct")
        else:
            yplot = 1 - np.array([response_curve(float(v), mapping) for v in x])
            title = "Angle → target • model"
            footer = f"{mapping['zero']:.1f}° → {mapping['maximum']:.1f}° • output 0–1"
        p.drawText(QRectF(10, 3, self.width()-20, 22), title)
        path=QPainterPath()
        for i, (xx, yy) in enumerate(zip(x, yplot)):
            point=(area.left()+float(xx)*area.width(), area.top()+float(yy)*area.height())
            path.moveTo(*point) if i == 0 else path.lineTo(*point)
        p.setPen(QPen(GREEN, 1.6)); p.drawPath(path); p.setPen(MUTED)
        p.drawText(QRectF(10, self.height()-23, self.width()-20, 22), footer)


class EffectModule(QWidget):
    def __init__(self, panel, effect):
        super().__init__(); self.panel, self.effect = panel, effect; self.live = {}
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.setMinimumWidth(360); self.setMaximumWidth(480)
        title=effect.title() + (" • Source pitch" if effect == "vibrato" else "")
        self.module=Module(title, list(FX_SPECS[effect].values()), panel.window.settings["effects"]["values"][effect], lambda key,value: panel.window.effect_changed(effect,key,value), header_keys={"on"})
        layout.addWidget(self.module)
        body=self.module.layout()
        body.takeAt(body.count()-1)  # No expanding spacer between parameters and mapping.
        for key, control in self.module.controls.items():
            control.findChild(QLabel).setText({"filterCutoff":"Filter Cutoff", "filterRq":"Filter Rq"}.get(key,key.title()))
        if effect in ("tremolo", "vibrato"):
            rate_spec = FX_SPECS[effect]["rate"]
            self.period=QDoubleSpinBox(); self.period.setDecimals(3); self.period.setRange(1000/rate_spec.maximum, 1000/rate_spec.minimum); self.period.setSuffix(" ms")
            self.period.setKeyboardTracking(False)
            self.period.valueChanged.connect(lambda value: panel.window.effect_changed(effect,"rate",1000/value))
            row=QHBoxLayout(); row.addWidget(QLabel("Period")); row.addWidget(self.period); row.addStretch(); body.addLayout(row)
            self.lfo=EffectPlot(self,True); body.addWidget(self.lfo)
        form=QFormLayout(); body.addLayout(form)
        self.source=QComboBox()
        for label,value in (("Manual","manual"),("Left pinch angle","left"),("Right pinch angle","right")): self.source.addItem(label,value)
        self.target=QComboBox()
        for value in TARGETS[effect]: self.target.addItem(value.title(),value)
        form.addRow("Input",self.source); form.addRow("Target",self.target)
        self.target.setToolTip("With angle input, the manual target parameter is the maximum mapped value.")
        self.target_note=QLabel("Angle input: manual target value sets the maximum.")
        self.target_note.setWordWrap(True); body.addWidget(self.target_note)
        self.live_label=QLabel("Angle not received • manual control"); self.live_label.setWordWrap(True); body.addWidget(self.live_label)
        self.source.currentIndexChanged.connect(lambda: self.change_mapping("source",self.source.currentData()))
        self.target.currentIndexChanged.connect(lambda: self.change_mapping("target",self.target.currentData()))
        self.advanced=QWidget(); advanced_form=QFormLayout(self.advanced)
        self.key_summary=QLabel(); body.addWidget(self.key_summary)
        self.details=Disclosure("Mapping / Key",self.advanced)
        self.details.toggle.toggled.connect(lambda: QTimer.singleShot(0, panel.relayout))
        body.addWidget(self.details)
        advanced_form.setContentsMargins(0,4,0,0)
        advanced_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        definition=QLabel("Thumb → Index in mirrored pixels: 0° right, +90° up; positive is counterclockwise. Fold uses 180° orientation. Angles near overlapping tips are invalid.")
        definition.setWordWrap(True); advanced_form.addRow(definition)
        self.mapping_refs={}
        for key,label,lo,hi,step,suffix in (
            ("zero","Zero Direction",-180,180,1,"°"),("maximum","Maximum Direction",-180,180,1,"°"),
            ("threshold","Zero Threshold",0,.99,.01,""),("smoothing","Smoothing",.005,2,.005," s"),
            ("deadband","Angle Deadband",0,15,.1,"°"),("min_separation","Minimum Separation",2,100,1," px"),
            ("bend","Curve Bend",1,8,.1,"")):
            spin=QDoubleSpinBox(); spin.setRange(lo,hi); spin.setDecimals(3); spin.setSingleStep(step); spin.setSuffix(suffix); spin.setKeyboardTracking(False)
            spin.valueChanged.connect(lambda value,key=key: self.change_mapping(key,value)); self.mapping_refs[key]=spin
            if key in ("zero","maximum"):
                row=QHBoxLayout(); row.addWidget(spin); row.addWidget(button("Capture",lambda checked=False,key=key:self.capture(key)))
                advanced_form.addRow(label,row)
            else: advanced_form.addRow(label,spin)
        for key,label,items in (("direction","Direction",("shortest","clockwise","counterclockwise")),("curve","Response Curve",("linear","slow","fast"))):
            combo=QComboBox()
            for item in items: combo.addItem(item.title(),item)
            combo.currentIndexChanged.connect(lambda value,key=key,combo=combo: self.change_mapping(key,combo.currentData()))
            self.mapping_refs[key]=combo; advanced_form.addRow(label,combo)
        for key,label in (("fold","Fold to 180° orientation"),("invert","Invert")):
            check=QCheckBox(); check.toggled.connect(lambda value,key=key: self.change_mapping(key,value))
            self.mapping_refs[key]=check; advanced_form.addRow(label,check)
        self.curve=EffectPlot(self); advanced_form.addRow(self.curve)
        self.key=QKeySequenceEdit(); self.key.setMaximumSequenceLength(1)
        self.key.editingFinished.connect(self.change_key)
        self.key_mode=QComboBox(); self.key_mode.addItem("Toggle","toggle"); self.key_mode.addItem("Hold","hold")
        self.key_mode.currentIndexChanged.connect(self.change_key)
        row=QHBoxLayout(); row.addWidget(self.key); row.addWidget(self.key_mode)
        advanced_form.addRow("On / Off Key",row)
        self.refresh()

    def capture(self,key):
        angle=self.live.get("angle")
        if angle is None: self.panel.window.show_error("No valid angle to capture. Select a hand and separate thumb / index tips.")
        else: self.change_mapping(key,angle)

    def change_mapping(self,key,value):
        self.panel.window.effect_mapping_changed(self.effect,key,value)

    def change_key(self):
        candidate=deepcopy(self.panel.window.settings["effects"])
        candidate["keys"][self.effect]={"key":self.key.keySequence().toString(QKeySequence.SequenceFormat.PortableText),"mode":self.key_mode.currentData()}
        try:
            candidate=validate_effects(candidate)
            self.panel.window.effect_keys.release_all()
            self.panel.window.settings["effects"]["keys"]=candidate["keys"]
        except Exception as exc: self.panel.window.show_error(str(exc))
        self.refresh()

    def refresh(self):
        settings=self.panel.window.settings["effects"]; values=settings["values"][self.effect]; mapping=settings["mappings"][self.effect]
        for key,control in self.module.controls.items(): control.show_value(values[key])
        if hasattr(self,"period"):
            self.period.blockSignals(True); self.period.setValue(1000/values["rate"]); self.period.blockSignals(False); self.lfo.update()
        for combo,value in ((self.source,mapping["source"]),(self.target,mapping["target"]),(self.key_mode,settings["keys"][self.effect]["mode"])):
            combo.blockSignals(True); combo.setCurrentIndex(combo.findData(value)); combo.blockSignals(False)
        for key,control in self.mapping_refs.items():
            control.blockSignals(True)
            if isinstance(control,QComboBox): control.setCurrentIndex(control.findData(mapping[key]))
            elif isinstance(control,QCheckBox): control.setChecked(mapping[key])
            else: control.setValue(mapping[key])
            control.blockSignals(False)
        self.key.blockSignals(True); self.key.setKeySequence(QKeySequence(settings["keys"][self.effect]["key"])); self.key.blockSignals(False)
        binding=settings["keys"][self.effect]
        self.target_note.setVisible(mapping["source"] != "manual")
        self.key_summary.setText(f"Key: {binding['key'] or '—'} · {binding['mode'].title()}")
        self.curve.update()

    def update_live(self,live):
        self.live=live or {}
        mapping=self.panel.window.settings["effects"]["mappings"][self.effect]
        if mapping["source"] == "manual": text="Manual • angle input bypassed"
        elif self.live.get("valid"):
            unit=FX_SPECS[self.effect][mapping["target"]].unit
            text=f"Angle {self.live['angle']:.1f}° • mapped {mapping['target']} {self.live['value']:.3f} {unit}"
        else:
            value=self.live.get("value",0.)
            text=f"No valid angle • {mapping['target']} {value:.3f} → zero effect"
        self.live_label.setText(text)
        if hasattr(self,"lfo"): self.lfo.update()


class EffectsPanel(QWidget):
    def __init__(self,window):
        super().__init__(); self.window=window
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        layout.addWidget(window.transport_bar())
        self.route=QLabel("Source + Vibrato → ordered FX → Output")
        self.route.setWordWrap(True); layout.addWidget(self.route)
        self.route.setToolTip("Vibrato changes source pitch before the audio FX. Koala stereo input uses a separate dry path. PANIC mutes both paths.")
        self.thru=button("Thru OFF",window.toggle_thru); self.thru.setCheckable(True)
        self.thru_level=QDoubleSpinBox(); self.thru_level.setRange(0,2); self.thru_level.setSingleStep(.01); self.thru_level.setValue(1); self.thru_level.setKeyboardTracking(False)
        self.thru_level.valueChanged.connect(window.set_thru_level)
        row=QHBoxLayout(); row.addWidget(QLabel("Dry input")); row.addWidget(self.thru); row.addWidget(QLabel("Level")); row.addWidget(self.thru_level); row.addStretch(); layout.addLayout(row)
        self.thru.setToolTip("Koala stereo input → dry Thru → output (outside the FX chain)")
        self.thru_level.setMaximumWidth(90)
        self.thru_status=QLabel("Input: not ready"); self.thru_status.setWordWrap(True)
        layout.addWidget(self.thru_status)
        self.order=QListWidget(); self.order.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.order.setFlow(QListView.Flow.LeftToRight); self.order.setWrapping(True)
        self.order.setResizeMode(QListView.ResizeMode.Adjust)
        self.order.setGridSize(QSize(106,30)); self.order.setFixedHeight(64)
        self.order.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.order.setToolTip("Audio FX order • drag to reorder, or select an effect and use Earlier / Later. Vibrato is source-side.")
        self.order.setAccessibleName("Audio FX processing order")
        self.set_order_items(window.settings["effects"]["order"])
        self.order.model().rowsMoved.connect(lambda *args: QTimer.singleShot(0,self.order_changed))
        chain=QHBoxLayout(); chain.addWidget(self.order,1)
        moves=QVBoxLayout(); moves.setSpacing(2)
        moves.addWidget(button("Earlier",lambda:self.move_effect(-1))); moves.addWidget(button("Later",lambda:self.move_effect(1)))
        chain.addLayout(moves); layout.addLayout(chain)
        self.rack=CardRack()
        self.modules={fx:EffectModule(self,fx) for fx in FX_NAMES}
        self.reflow()
        self.area=QScrollArea(); self.area.setWidgetResizable(True); self.area.setWidget(self.rack); layout.addWidget(self.area,1)
        self.area.viewport().installEventFilter(self)
        self.order.viewport().installEventFilter(self)
        self.timer=QTimer(self); self.timer.timeout.connect(self.update_live); self.timer.start(100)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Resize:
            if obj is self.area.viewport(): self.rack.reflow(event.size().width())
            elif obj is self.order.viewport():
                columns=max(1,event.size().width()//106)
                self.order.setFixedHeight(math.ceil(5/columns)*30+4)
        return super().eventFilter(obj,event)

    def relayout(self):
        for module in self.modules.values():
            module.module.layout().invalidate(); module.module.layout().activate()
            module.layout().invalidate(); module.layout().activate()
            module.updateGeometry()
        self.rack.grid.invalidate()
        self.rack.columns = 0
        self.rack.reflow(self.area.viewport().width())
        self.rack.grid.activate()
        self.rack.updateGeometry()

    def set_order_items(self, order):
        self.order.clear()
        for effect in order:
            item=QListWidgetItem(effect.title())
            item.setData(Qt.ItemDataRole.UserRole,effect)
            self.order.addItem(item)

    def move_effect(self,direction):
        at=self.order.currentRow(); new=at+direction
        if at>=0 and 0<=new<self.order.count():
            item=self.order.takeItem(at); self.order.insertItem(new,item); self.order.setCurrentRow(new); self.order_changed()

    def order_changed(self):
        order=[self.order.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.order.count())]
        self.window.effect_order_changed(order)
        self.reflow()

    def reflow(self):
        order=self.window.settings["effects"]["order"]
        self.rack.set_cards([self.modules[fx] for fx in ["vibrato",*order]])
        for i,fx in enumerate(order,1):
            self.modules[fx].module.findChild(QLabel,"heading").setText(f"{i} · {fx.title()}")
        for i in range(self.order.count()):
            item=self.order.item(i)
            item.setText(f"{i+1} · {item.data(Qt.ItemDataRole.UserRole).title()}")
            item.setToolTip(item.text())

    def refresh(self):
        for module in self.modules.values(): module.refresh()
        current=[self.order.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.order.count())]
        if current != self.window.settings["effects"]["order"]:
            self.order.blockSignals(True); self.set_order_items(self.window.settings["effects"]["order"]); self.order.blockSignals(False); self.reflow()
        self.thru.setChecked(self.window.thru_on); self.thru.setText("Thru ON" if self.window.thru_on else "Thru OFF")

    def update_live(self):
        if not self.isVisible(): return
        worker=self.window.worker
        live=worker.angle_readouts() if worker and hasattr(worker,"angle_readouts") else {}
        for fx,module in self.modules.items():
            # Update readouts but paint only visible cards via Qt's update coalescing.
            module.update_live(live.get(fx))
