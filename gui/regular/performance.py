"""Bounded measurements of software stages, not physical hand-to-sound latency."""
from collections import deque
import json
import math
import threading
import time


def distribution(values):
    ordered = sorted(float(x) for x in values if math.isfinite(x))
    if not ordered:
        return None
    def percentile(p):
        at = (len(ordered) - 1) * p
        lo = int(at)
        return ordered[lo] + (ordered[min(lo + 1, len(ordered) - 1)] - ordered[lo]) * (at - lo)
    return {"median": percentile(.5), "p95": percentile(.95), "max": ordered[-1]}


class PerformanceRecorder:
    def __init__(self, capacity=10000):
        self.lock = threading.Lock()
        self.samples = deque(maxlen=capacity)
        self.display = deque(maxlen=capacity)
        self.overwritten = 0
        self.sequence = 0

    def control(self, values):
        with self.lock:
            self.sequence += 1
            self.samples.append(dict(values, sequence=self.sequence, at=time.perf_counter()))
            return self.sequence

    def shown(self, values):
        with self.lock:
            self.display.append(dict(values))

    def overwrite(self):
        with self.lock:
            self.overwritten += 1

    def reset(self):
        with self.lock:
            self.samples.clear(); self.display.clear(); self.overwritten = 0

    def summary(self, recent=None):
        with self.lock:
            samples, display, overwritten = list(self.samples), list(self.display), self.overwritten
        if recent:
            samples, display = samples[-recent:], display[-recent:]
        fields = sorted({k for row in samples + display for k in row if k.endswith("_ms")})
        duration = samples[-1]["at"] - samples[0]["at"] if len(samples) > 1 else 0
        return {
            "scope": "Software timing only; no sensor timestamp, DAC or acoustic measurement",
            "camera_buffer_age": "unknown (OpenCV read completion is the timestamp)",
            "camera_dropped_frames": "unknown (camera frame sequence is unavailable)",
            "control_frames": len(samples), "display_paints": len(display),
            "display_frames_superseded": overwritten, "display_queue_capacity": 1,
            "fps": (len(samples) - 1) / duration if duration else 0,
            "timings_ms": {key: distribution([r[key] for r in samples + display if key in r]) for key in fields},
            "detected_hands": distribution([r.get("hands", 0) for r in samples]),
        }

    def save(self, path, **metadata):
        from pathlib import Path
        target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({**metadata, **self.summary()}, indent=2), encoding="utf-8")
