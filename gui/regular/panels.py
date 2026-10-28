"""Presentation-only containers: docking, disclosures and bounded card grids."""
from PySide6.QtCore import Qt, QTimer, QEvent, QPoint, QRect
from PySide6.QtWidgets import (QApplication, QWidget, QDockWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLabel, QPushButton, QToolButton, QMenu, QSizePolicy)


class Disclosure(QWidget):
    def __init__(self, title, content, expanded=False):
        super().__init__()
        self.content = content
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.toggle = QToolButton()
        self.toggle.setText(title); self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.toggled.connect(self.set_expanded)
        layout.addWidget(self.toggle); layout.addWidget(content)
        self.set_expanded(expanded)

    def set_expanded(self, expanded):
        self.toggle.setChecked(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)


class CardRack(QWidget):
    """Stable row-major order; resizing never changes the processing order."""
    def __init__(self):
        super().__init__()
        self.grid = QGridLayout(self); self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(10)
        self.cards = []; self.columns = 0
        self.setMinimumWidth(376)

    def set_cards(self, cards):
        self.cards = cards
        self.columns = 0
        self.reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event); self.reflow()

    def reflow(self, available_width=None):
        columns = max(1, min(3, ((self.width() if available_width is None else available_width) - 6) // 370))
        if columns == self.columns: return
        self.columns = columns
        while self.grid.count(): self.grid.takeAt(0)
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // columns, i % columns, Qt.AlignmentFlag.AlignTop)
        for i in range(4): self.grid.setColumnStretch(i, 1 if i < columns else 0)
        for i in range(len(self.cards) + 1): self.grid.setRowStretch(i, 0)
        self.grid.setRowStretch((len(self.cards) + columns - 1) // columns, 1)


class AdaptiveSettings(QWidget):
    """Keep left/right hands side by side, wrapping each side internally."""
    def __init__(self, callback):
        super().__init__(); self.callback = callback

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.callback(self.width() < 650)


class PanelDock(QDockWidget):
    def __init__(self, name, owner, content):
        super().__init__(name, owner)
        self.setObjectName(name)
        self.pinned = False; self.locked = False; self.lock_position = None
        self._moving = False
        self.setWidget(content)
        title = QWidget(); title.setObjectName("panelTitle")
        row = QHBoxLayout(title); row.setContentsMargins(8, 3, 5, 3); row.setSpacing(6)
        self.heading = QLabel(name); self.heading.setObjectName("panelHeading")
        row.addWidget(self.heading, 1)
        self.detach = QPushButton("Detach")
        self.detach.clicked.connect(lambda: self.setFloating(not self.isFloating()))
        row.addWidget(self.detach)
        self.pin = QPushButton("Pin")
        self.pin.setCheckable(True); self.pin.setToolTip("Always on Top • above other applications")
        self.pin.setAccessibleName("Always on Top")
        self.pin.toggled.connect(self.set_pinned); row.addWidget(self.pin)
        more = QToolButton(); more.setText("..."); more.setAccessibleName(name + " panel options")
        menu = QMenu(more)
        self.lock_action = menu.addAction("Lock Position"); self.lock_action.setCheckable(True)
        self.lock_action.toggled.connect(self.set_locked)
        menu.addAction("Bring to Front", self.bring_forward)
        menu.addAction("Recover Windows", owner.recover_windows)
        menu.addAction("Audio Setup…", owner.open_audio_setup)
        menu.addSeparator(); menu.addAction("Hide Panel", self.hide)
        more.setMenu(menu); more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        row.addWidget(more); self.setTitleBarWidget(title)
        self.topLevelChanged.connect(self.floating_changed)
        self.set_locked(False); self.floating_changed(False)

    def floating_changed(self, floating):
        self.parentWidget().effect_keys.release_all()
        self.detach.setText("Dock" if floating else "Detach")
        self.pin.setVisible(floating)
        for transport in self.widget().findChildren(QWidget, "localTransport"):
            transport.setVisible(floating)
        # A remembered pin applies only while detached.
        self._apply_pin()
        self.lock_position = self.pos() if self.locked and floating else None

    def set_pinned(self, enabled):
        self.parentWidget().effect_keys.release_all()
        self.pinned = bool(enabled)
        self.pin.blockSignals(True); self.pin.setChecked(self.pinned); self.pin.blockSignals(False)
        self.pin.setText("Pinned" if self.pinned else "Pin")
        self._apply_pin()

    def _apply_pin(self):
        desired = self.isFloating() and self.pinned
        if bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) == desired: return
        geometry, visible = self.geometry(), self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, desired)
        self.setGeometry(geometry)
        if visible: self.show()

    def set_locked(self, enabled):
        self.locked = bool(enabled)
        self.lock_action.blockSignals(True); self.lock_action.setChecked(self.locked); self.lock_action.blockSignals(False)
        features = QDockWidget.DockWidgetFeature.DockWidgetClosable
        if not self.locked:
            features |= QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        self.setFeatures(features); self.detach.setEnabled(not self.locked)
        self.lock_position = self.pos() if self.locked and self.isFloating() else None

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.locked and self.isFloating() and self.lock_position is not None and not self._moving:
            self._moving = True
            self.move(self.lock_position)
            self._moving = False

    def recover(self, force=False):
        if not self.isFloating(): return
        screens = [screen.availableGeometry() for screen in QApplication.screens()]
        rect = self.frameGeometry()
        title = QRect(rect.x(), rect.y(), rect.width(), 38)
        if not force and any(s.contains(title) for s in screens): return
        target = max(screens, key=lambda s: s.intersected(rect).width() * s.intersected(rect).height())
        locked = self.locked; self.set_locked(False)
        self.resize(min(self.width(), target.width() - 32), min(self.height(), target.height() - 64))
        self.move(target.topLeft() + QPoint(16, 32))
        self.set_locked(locked)

    def bring_forward(self):
        self.show(); self.recover(); self.raise_(); self.activateWindow()
