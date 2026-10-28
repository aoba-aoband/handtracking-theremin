"""Application-wide FX keys with text-entry, repeat and focus protections."""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit, QComboBox, QKeySequenceEdit


class EffectKeys(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window, self.held, self.pressed = window, {}, set()
        self.physical = {}
        QApplication.instance().installEventFilter(self)

    def release_all(self):
        held, self.held = self.held, {}
        self.pressed.clear()
        self.physical.clear()
        for effect, old in held.values(): self.window.effect_changed(effect, "on", old)

    def close(self):
        self.release_all()
        QApplication.instance().removeEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.ApplicationDeactivate, QEvent.Type.WindowDeactivate):
            self.release_all()
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease): return False
        key = QKeySequence(event.keyCombination()).toString(QKeySequence.SequenceFormat.PortableText)
        if event.type() == QEvent.Type.KeyRelease:
            if event.isAutoRepeat(): return key in self.pressed
            key = self.physical.pop(event.key(), key)
            self.pressed.discard(key)
            if key in self.held:
                effect, old = self.held.pop(key)
                self.window.effect_changed(effect, "on", old)
                return True
            return False
        focused = QApplication.focusWidget()
        while focused:
            if isinstance(focused, (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit, QComboBox, QKeySequenceEdit)):
                return False
            focused = focused.parentWidget()
        binding = next(((fx, b) for fx, b in self.window.settings["effects"]["keys"].items() if b["key"] == key), None)
        if binding is None: return False
        if event.isAutoRepeat() or key in self.pressed or event.key() in self.physical: return True
        self.pressed.add(key)
        self.physical[event.key()] = key
        effect, options = binding
        old = self.window.settings["effects"]["values"][effect]["on"]
        if options["mode"] == "hold": self.held[key] = (effect, old)
        self.window.effect_changed(effect, "on", 1 if options["mode"] == "hold" else 1 - old)
        return True
