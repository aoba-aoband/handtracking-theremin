"""Worker reusing the existing tracker, mapper, octave and OSC event path."""
from copy import deepcopy
import threading
import time

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from src.hand_tracker import MediaPipeHandsSmokeTest


class CameraWorker(QThread):
    frame = Signal(QImage, object, object, float)
    failure = Signal(str)

    def __init__(self, index, model_path, mapping, event_sink):
        super().__init__()
        self.index, self.model_path = index, model_path
        self.mapping = deepcopy(mapping)
        self.event_sink = event_sink
        self.lock = threading.Lock()

    def configure(self, mapping):
        with self.lock:
            self.mapping = deepcopy(mapping)

    def run(self):
        tracker = MediaPipeHandsSmokeTest(
            camera_index=self.index, model_path=self.model_path,
            sample_mapping=True, event_sink=self.event_sink,
        )
        previous = time.monotonic()
        try:
            tracker.start()
            while not self.isInterruptionRequested():
                with self.lock:
                    tracker.sample_mapper.mapping_config = deepcopy(self.mapping)
                frame = tracker.draw_landmarks(tracker.read())
                rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
                image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()
                now = time.monotonic()
                self.frame.emit(image, tracker.current_sample_features, tracker.current_sample_events, 1 / max(.001, now - previous))
                previous = now
        except Exception as exc:
            self.failure.emit(str(exc))
        finally:
            tracker.stop()
