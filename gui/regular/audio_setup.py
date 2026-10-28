"""Machine-local, OS-specific audio selection. Only SC enumerates devices."""
import json
import platform
from pathlib import Path
import re

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QLabel,
                              QHBoxLayout, QPushButton, QDoubleSpinBox)


def validate_audio(data):
    if not isinstance(data, dict) or set(data) != {"input", "output", "sample_rate"}: raise ValueError("Invalid audio settings")
    if any(v is not None and not isinstance(v, str) for v in (data["input"], data["output"])): raise ValueError("Invalid audio device name")
    rate = data["sample_rate"]
    if rate is not None and (isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate not in (22050, 32000, 44100, 48000, 88200, 96000, 192000)):
        raise ValueError("Unsupported sample rate")
    return dict(data)


def device_api(name):
    match = re.match(r"\s*(.*?)\s*:\s", name or "")
    return match[1].strip().lower() if match else None


def device_warnings(config, system=None):
    system = system or platform.system()
    source, output = config["input"], config["output"]
    if system == "Windows" and source not in (None, "none") and output is not None:
        a, b = device_api(source), device_api(output)
        if a and b and a != b: return "Input / output use different Windows APIs. Select a compatible API pair; this combination may not boot."
    if system == "Darwin":
        return ("For iPad / Koala input and UR44C output, match their sample rates in Audio MIDI Setup. "
                "Different input/output devices use sampleRate = nil here. If boot fails, inspect the log and try an Aggregate Device. This does not guarantee stable startup.")
    return "Windows keeps the SC default rate unless you explicitly select a rate. Changes require a muted server restart."


def available(config, devices):
    return ((config["input"] in (None, "none") or config["input"] in devices.get("input", []))
            and (config["output"] is None or config["output"] in devices.get("output", [])))


class MachineAudio:
    def __init__(self, directory, system=None):
        self.path = Path(directory) / "audio-setup.json"
        self.system = system or platform.system()

    def load(self):
        if not self.path.exists(): return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != 1: raise ValueError("Unsupported Audio Setup format")
        config = data.get("profiles", {}).get(self.system)
        return validate_audio(config) if config is not None else None

    def save(self, config):
        config = validate_audio(config)
        data = {"version": 1, "profiles": {}}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("version") != 1 or not isinstance(data.get("profiles"), dict): raise ValueError("Unsupported Audio Setup format")
            except (ValueError, TypeError):
                # Applying is an explicit repair. Preserve the unreadable file.
                import uuid
                self.path.replace(self.path.with_name("audio-setup.invalid-" + uuid.uuid4().hex[:8] + ".json"))
                data = {"version": 1, "profiles": {}}
        data["profiles"][self.system] = config
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8"); tmp.replace(self.path)

    def thru_level(self):
        path = self.path.parent / ("thru-" + self.system + ".json")
        if not path.exists(): return 1.
        level = json.loads(path.read_text(encoding="utf-8"))["level"]
        if not isinstance(level, (float, int)) or not 0 <= level <= 2: raise ValueError("Invalid machine Thru level")
        return float(level)

    def save_thru_level(self, level):
        if not 0 <= level <= 2: raise ValueError("Invalid Thru level")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        (self.path.parent / ("thru-" + self.system + ".json")).write_text(json.dumps({"level": level}), encoding="utf-8")


class AudioSetup(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Audio Setup")
        self.resize(650, 360)
        layout = QVBoxLayout(self)
        self.message = QLabel("Device candidates are reported by SuperCollider before audio-server boot.")
        self.message.setWordWrap(True); layout.addWidget(self.message)
        form = QFormLayout(); layout.addLayout(form)
        self.input = QComboBox(); self.output = QComboBox(); self.rate = QComboBox()
        form.addRow("Input (stereo 1 / 2)", self.input); form.addRow("Output (stereo 1 / 2)", self.output)
        self.rate.addItem("SC / hardware default", None)
        for rate in (22050, 32000, 44100, 48000, 88200, 96000, 192000): self.rate.addItem(f"{rate} Hz", rate)
        form.addRow("Sample Rate", self.rate)
        self.advice = QLabel(); self.advice.setWordWrap(True); layout.addWidget(self.advice)
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        row = QHBoxLayout(); layout.addLayout(row)
        for label, callback in (("Refresh Devices", self.refresh), ("Open SC Log", self.open_log),
                                ("Apply / Restart SC", self.apply), ("Close", self.close)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
            if label.startswith("Apply"): self.apply_button = button
        for combo in (self.input, self.output, self.rate): combo.currentIndexChanged.connect(self.explain)
        self.populate()

    def current(self):
        config = {"input": self.input.currentData(), "output": self.output.currentData(), "sample_rate": self.rate.currentData()}
        if platform.system() == "Darwin" and config["input"] != "none" and config["input"] != config["output"]:
            config["sample_rate"] = None
        return validate_audio(config)

    def populate(self, config=None):
        config = config or self.window.audio_config or {"input": "none", "output": None, "sample_rate": None}
        for kind, combo in (("input", self.input), ("output", self.output)):
            combo.blockSignals(True); combo.clear()
            if kind == "input": combo.addItem("None (internal instrument only)", "none")
            combo.addItem("System default", None)
            for name in self.window.bridge.devices.get(kind, []): combo.addItem(name, name)
            index = combo.findData(config[kind])
            if index < 0:
                combo.addItem("Unavailable: " + str(config[kind]), config[kind]); index = combo.count() - 1
            combo.setCurrentIndex(index); combo.blockSignals(False)
        self.rate.setCurrentIndex(max(0, self.rate.findData(config["sample_rate"])))
        self.explain()

    def explain(self):
        config = self.current()
        self.advice.setText(device_warnings(config))
        ready = self.window.bridge.connected and self.window.bridge.devices_received
        valid = available(config, self.window.bridge.devices)
        self.apply_button.setEnabled(ready and valid)
        if not ready: self.status.setText("Waiting for SC device enumeration; audio server is not started.")
        elif not valid: self.status.setText("Previous device is unavailable. Choose devices explicitly; no automatic substitution or playback.")
        elif self.window.bridge.audio_status.get("error"):
            self.status.setText(self.window.bridge.audio_status["error"] + "\nSelect devices and Apply / Restart SC to retry.")
        elif self.window.bridge.audio_status.get("state") == "unconfigured":
            self.status.setText("Audio is not configured. Select devices and Apply / Restart SC, wait for Audio ready, then press Start.")
        else: self.status.setText("Apply stops the camera, mutes both paths and restarts the audio server. Start is required afterward.")

    def refresh(self):
        if not self.window.bridge.connected: self.window.launch_sc()
        self.window.bridge.request("devices")

    def open_log(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.window.bridge.log_path)))

    def apply(self):
        try:
            config = self.current()
            if not available(config, self.window.bridge.devices): raise ValueError("Select available audio devices")
            self.window.machine_audio.save(config)
            self.window.audio_config = config
            self.window.audio_load_error = None
            self.window.audio_prompted = False
            self.window.stop()
            self.window.thru_on = False
            self.window.synced = False
            self.window.bridge.configure_audio(config)
            self.window.camera_status.setText("Audio restarting • press Start when ready")
            self.status.setText("Restart requested. Waiting for SC; performance and Thru remain muted.")
        except Exception as exc: self.status.setText(str(exc))
