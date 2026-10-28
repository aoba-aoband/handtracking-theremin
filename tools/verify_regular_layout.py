"""Render isolated offline UI layouts; no camera, OSC or user settings are used.

Set QT_SCALE_FACTOR before launch to exercise Qt display scaling. This does not
change Windows display settings or emulate mixed-DPI monitor transitions.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from gui.regular.app import InstrumentWindow, STYLE
from gui.regular.state import Store


class OfflineBridge(QObject):
    state = Signal(str, dict)
    telemetry = Signal(str, dict)
    error = Signal(str)
    connected = False
    busy = False

    def request(self, *args): pass
    def panic(self): pass
    def tick(self): pass
    def close(self): pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    font = Path("C:/Windows/Fonts/segoeui.ttf")
    if font.exists(): QFontDatabase.addApplicationFont(str(font))
    app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    report = {"scale": os.environ.get("QT_SCALE_FACTOR", "1"), "layouts": [], "effects": []}

    def settle():
        for _ in range(12): app.processEvents()

    with tempfile.TemporaryDirectory() as temporary:
        window = InstrumentWindow(store=Store(temporary), bridge=OfflineBridge())
        window.timer.stop(); window.show()
        try:
            for width, height in ((1366,768),(1920,1080)):
                window.resize(width,height); settle(); window.update_system_status()
                window.grab().save(str(args.out / f"main-{width}.png"))
                report["layouts"].append({"requested": [width,height], "actual": list(window.size().toTuple()),
                    "panels": {name: list(dock.size().toTuple()) for name,dock in window.docks.items()}})
            dock = window.docks["Effects"]; dock.setFloating(True)
            for width in (400,740,760,800,1110,1140,1200,400):
                started = time.perf_counter()
                dock.resize(width,850); settle()
                panel = window.effects_panel
                record = {"width": width, "actual_width": dock.width(), "columns": panel.rack.columns,
                          "horizontal_scroll": panel.area.horizontalScrollBar().maximum(),
                          "card_widths": [card.width() for card in panel.rack.cards],
                          "settle_ms": round((time.perf_counter()-started)*1000,2)}
                report["effects"].append(record)
                assert record["horizontal_scroll"] == 0, record
                assert all(w <= 480 for w in record["card_widths"]), record
                if width in (400,800,1200): dock.grab().save(str(args.out / f"effects-{width}.png"))
            window.camera_settings_toggle.click()
            camera=window.docks["Camera"]; camera.setFloating(True); camera.resize(420,760); settle()
            camera.grab().save(str(args.out / "camera-settings.png"))
            controls=window.docks["Controls"]; controls.setFloating(True); controls.resize(800,900)
            for probe in (0,1):
                window.select_probe(probe); settle()
                controls.grab().save(str(args.out / f"controls-{probe}.png"))
            analysis=window.docks["Analysis"]; analysis.setFloating(True); analysis.resize(500,650); settle()
            analysis.grab().save(str(args.out / "analysis-no-data.png"))
        finally:
            window.close(); settle()
    (args.out / "measurements.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report),flush=True)


if __name__ == "__main__": main()
