"""Worker reusing the existing tracker, mapper, octave and OSC event path."""
from copy import deepcopy
import threading
import time

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from src.hand_tracker import MediaPipeHandsSmokeTest
from .performance import PerformanceRecorder
from .effects import FX_SPECS
from src.angle_mapping import AngleMapper


class CameraWorker(QThread):
    frame = Signal(QImage, object, object, float)
    failure = Signal(str)

    def __init__(self, index, model_path, mapping, event_sink):
        super().__init__()
        self.index, self.model_path = index, model_path
        self.mapping = deepcopy(mapping)
        self.event_sink = event_sink
        self.lock = threading.Lock()
        self.metrics = PerformanceRecorder()
        self.draw_enabled = True
        self.effects = None
        self.mod_sink = None
        self.angles = AngleMapper()
        self.live_angles = {}

    def configure(self, mapping):
        with self.lock:
            self.mapping = deepcopy(mapping)

    def configure_effects(self, effects, mod_sink):
        with self.lock:
            self.effects, self.mod_sink = deepcopy(effects), mod_sink

    def angle_readouts(self):
        with self.lock: return deepcopy(self.live_angles)

    def process_angles(self, features, width, height, dt):
        with self.lock: effects, sink = self.effects, self.mod_sink
        if effects is None or sink is None: return (0., 0.)
        mapping_started = time.perf_counter()
        hands = {f.handedness.lower(): f for f in features}
        readouts, packets = {}, []
        for effect, config in effects["mappings"].items():
            if config["source"] == "manual": continue
            result = self.angles.update(effect, hands.get(config["source"]), width, height, config, dt)
            target = config["target"]; spec = FX_SPECS[effect][target]
            result["value"] = spec.minimum + (effects["values"][effect][target] - spec.minimum) * result["normalized"]
            readouts[effect] = result
            packets.append((effect, target, result["value"], result["presence"]))
        mapping_ms = (time.perf_counter() - mapping_started) * 1000
        send_started = time.perf_counter()
        for packet in packets: sink(*packet)
        send_ms = (time.perf_counter() - send_started) * 1000
        with self.lock: self.live_angles = readouts
        return mapping_ms, send_ms

    def run(self):
        tracker = MediaPipeHandsSmokeTest(
            camera_index=self.index, model_path=self.model_path,
            sample_mapping=True, event_sink=self.event_sink,
        )
        previous = time.perf_counter()
        tracker.feature_processor = lambda features, width, height: self.process_angles(features, width, height, time.perf_counter() - previous)
        try:
            tracker.start()
            while not self.isInterruptionRequested():
                with self.lock:
                    tracker.sample_mapper.mapping_config = deepcopy(self.mapping)
                started = time.perf_counter()
                frame = tracker.read()
                captured_at = time.perf_counter()
                timings = {"camera_capture_ms": (time.perf_counter() - started) * 1000}
                frame = tracker.draw_landmarks(frame, timings=timings, draw=self.draw_enabled)
                timings["read_to_osc_ms"] = (tracker.control_ready_at - captured_at) * 1000
                drawing = time.perf_counter()
                rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
                image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()
                timings["drawing_ms"] += (time.perf_counter() - drawing) * 1000
                timings["total_frame_ms"] = (time.perf_counter() - started) * 1000
                timings["hands"] = len(tracker.current_features)
                sequence = self.metrics.control(timings)
                image.setText("capturedAt", str(captured_at))
                image.setText("sequence", str(sequence))
                now = time.perf_counter()
                self.frame.emit(image, tracker.current_sample_features, tracker.current_sample_events, 1 / max(.001, now - previous))
                previous = now
        except Exception as exc:
            self.failure.emit(str(exc))
        finally:
            tracker.stop()
