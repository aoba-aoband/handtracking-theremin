"""Map extracted hand features into generic control events.

Mappings should be configurable so the platform can target SuperCollider,
Ableton Live, Max for Live, or other systems without hard-coded gesture roles.
"""

import time

from src.features import HandFeatures
from src.pitch import (
    norm_to_freq as _norm_to_freq,
    quantize_freq_to_scale,
)


DEFAULT_MIN_FREQ = 220.0
DEFAULT_MAX_FREQ = 880.0
DEFAULT_ARTICULATION_GATE_ON_THRESHOLD = 0.65
DEFAULT_ARTICULATION_GATE_OFF_THRESHOLD = 0.45
DEFAULT_ARTICULATION_HAND_LOSS_RELEASE_SECONDS = 0.25
MIN_ARTICULATION_THRESHOLD_GAP = 0.000001
ARTICULATION_GATE_ADDRESS = "/sample/left/articulation/gate"


class ControlEvent:
    """A generic control message produced from hand-derived features."""

    def __init__(self, address, value, metadata=None):
        self.address = address
        self.value = value
        self.metadata = metadata or {}


class Mapper:
    """Convert feature dictionaries into generic control events."""

    def __init__(self, mapping_config=None):
        self.mapping_config = mapping_config or {}

    def map(self, features):
        """Return control events for the given feature values."""
        raise NotImplementedError


class HandFeatureMapper(Mapper):
    """Map neutral hand features to generic hand control events."""

    def map(self, features):
        """Return generic control events for one or more hands."""
        if isinstance(features, HandFeatures):
            features = [features]

        events = []
        for hand_index, hand_features in enumerate(features or []):
            events.extend(map_hand_features(hand_features, hand_index))

        return events


class SampleMusicalMapper(Mapper):
    """Map neutral hand features to sample musical control events."""

    def __init__(self, mapping_config=None, clock=None):
        super().__init__(mapping_config=mapping_config)
        self.articulation_tracker = LeftArticulationGateTracker(
            mapping_config=self.mapping_config,
            clock=clock,
        )

    def map(self, features):
        """Return sample events based on MediaPipe handedness labels."""
        if isinstance(features, HandFeatures):
            features = [features]

        self.articulation_tracker.configure(self.mapping_config)
        events = []
        left_hand = None
        for hand_index, hand_features in enumerate(features or []):
            events.extend(
                map_sample_musical_features(
                    hand_features,
                    hand_index,
                    self.mapping_config,
                )
            )
            handedness = (hand_features.handedness or "").strip().lower()
            if handedness == "left" and left_hand is None:
                left_hand = (hand_features, hand_index)

        if left_hand is not None:
            hand_features, hand_index = left_hand
            events.append(
                self.articulation_tracker.update_left_hand(
                    hand_features,
                    hand_index,
                )
            )
        else:
            event = self.articulation_tracker.update_left_hand_missing()
            if event is not None:
                events.append(event)

        return events

    def update_articulation_settings(self, mapping_config):
        """Apply runtime articulation settings without replacing the tracker."""
        self.mapping_config.update(mapping_config)
        self.articulation_tracker.update_settings(
            on_threshold=self.mapping_config.get(
                "articulation_gate_on_threshold",
            ),
            off_threshold=self.mapping_config.get(
                "articulation_gate_off_threshold",
            ),
            hand_loss_release_seconds=self.mapping_config.get(
                "articulation_hand_loss_release_seconds",
            ),
        )


class LeftArticulationGateTracker:
    """Track a hysteretic left-pinch articulation gate for sample mapping."""

    def __init__(self, mapping_config=None, clock=None):
        self.clock = clock or time.monotonic
        self.gate = 0
        self.last_left_seen_at = None
        self.configure(mapping_config)

    def configure(self, mapping_config=None):
        """Apply a sanitized sample-mapping config without resetting gate state."""
        config = mapping_config or {}
        self.update_settings(
            on_threshold=config.get(
                "articulation_gate_on_threshold",
                DEFAULT_ARTICULATION_GATE_ON_THRESHOLD,
            ),
            off_threshold=config.get(
                "articulation_gate_off_threshold",
                DEFAULT_ARTICULATION_GATE_OFF_THRESHOLD,
            ),
            hand_loss_release_seconds=config.get(
                "articulation_hand_loss_release_seconds",
                DEFAULT_ARTICULATION_HAND_LOSS_RELEASE_SECONDS,
            ),
        )

    def update_settings(
        self,
        on_threshold=None,
        off_threshold=None,
        hand_loss_release_seconds=None,
    ):
        """Update calibration while preserving gate and hand-loss timing state."""
        current_on = getattr(
            self,
            "on_threshold",
            DEFAULT_ARTICULATION_GATE_ON_THRESHOLD,
        )
        current_off = getattr(
            self,
            "off_threshold",
            DEFAULT_ARTICULATION_GATE_OFF_THRESHOLD,
        )
        current_release = getattr(
            self,
            "hand_loss_release_seconds",
            DEFAULT_ARTICULATION_HAND_LOSS_RELEASE_SECONDS,
        )
        settings = _sanitize_articulation_settings(
            current_on if on_threshold is None else on_threshold,
            current_off if off_threshold is None else off_threshold,
            (
                current_release
                if hand_loss_release_seconds is None
                else hand_loss_release_seconds
            ),
        )
        self.on_threshold = settings["articulation_gate_on_threshold"]
        self.off_threshold = settings["articulation_gate_off_threshold"]
        self.hand_loss_release_seconds = settings[
            "articulation_hand_loss_release_seconds"
        ]

    def update_left_hand(self, features, hand_index=0):
        """Update gate state from the visible left hand and return its event."""
        pinch = _clamp(_safe_float(features.pinch, 0.0), 0.0, 1.0)
        if pinch >= self.on_threshold:
            self.gate = 1
        elif pinch <= self.off_threshold:
            self.gate = 0

        self.last_left_seen_at = self.now()
        return self.build_event(features=features, hand_index=hand_index)

    def update_left_hand_missing(self):
        """Repeat release after timeout so a lost UDP packet cannot latch gate."""
        if self.last_left_seen_at is None:
            return None

        elapsed = self.now() - self.last_left_seen_at
        if elapsed < self.hand_loss_release_seconds:
            return None

        self.gate = 0
        return self.build_event(reason="left_hand_loss_timeout")

    def now(self):
        """Return the current monotonic time."""
        return self.clock()

    def build_event(self, features=None, hand_index=None, reason=None):
        """Build the current articulation gate ControlEvent."""
        metadata = {
            "source_hand_index": hand_index,
            "mapping": "sample_musical",
            "feature": "pinch",
            "role": "articulation_gate",
            "gate_on_threshold": self.on_threshold,
            "gate_off_threshold": self.off_threshold,
        }
        if features is not None:
            metadata.update(
                {
                    "handedness": features.handedness,
                    "landmarks_count": features.landmarks_count,
                }
            )
        if reason is not None:
            metadata["reason"] = reason

        return ControlEvent(ARTICULATION_GATE_ADDRESS, self.gate, metadata)


def map_hand_features(features, hand_index=0):
    """Convert one HandFeatures object into generic ControlEvents."""
    metadata = {
        "hand_index": hand_index,
        "handedness": features.handedness,
        "landmarks_count": features.landmarks_count,
    }
    prefix = f"/hand/{hand_index}"

    return [
        ControlEvent(
            f"{prefix}/index/x",
            features.index_tip_x,
            {**metadata, "feature": "index_tip_x"},
        ),
        ControlEvent(
            f"{prefix}/index/y",
            features.index_tip_y,
            {**metadata, "feature": "index_tip_y"},
        ),
        ControlEvent(
            f"{prefix}/middle/x",
            features.middle_tip_x,
            {**metadata, "feature": "middle_tip_x"},
        ),
        ControlEvent(
            f"{prefix}/middle/y",
            features.middle_tip_y,
            {**metadata, "feature": "middle_tip_y"},
        ),
        ControlEvent(
            f"{prefix}/thumb/x",
            features.thumb_tip_x,
            {**metadata, "feature": "thumb_tip_x"},
        ),
        ControlEvent(
            f"{prefix}/thumb/y",
            features.thumb_tip_y,
            {**metadata, "feature": "thumb_tip_y"},
        ),
        ControlEvent(
            f"{prefix}/pinch",
            features.pinch,
            {**metadata, "feature": "pinch"},
        ),
    ]


def map_sample_musical_features(features, hand_index=0, mapping_config=None):
    """Convert one HandFeatures object into sample mapping ControlEvents."""
    mapping_config = mapping_config or {}
    pitch_min_freq = mapping_config.get("pitch_min_freq", DEFAULT_MIN_FREQ)
    pitch_max_freq = mapping_config.get("pitch_max_freq", DEFAULT_MAX_FREQ)
    quantize_pitch = bool(mapping_config.get("quantize_pitch", False))
    pitch_root = mapping_config.get("pitch_root", "A")
    pitch_scale = mapping_config.get("pitch_scale", "minor-pentatonic")
    handedness = (features.handedness or "").strip().lower()
    metadata = {
        "source_hand_index": hand_index,
        "handedness": features.handedness,
        "landmarks_count": features.landmarks_count,
        "mapping": "sample_musical",
    }

    if handedness == "right":
        inverted_y = max(0.0, min(1.0, 1.0 - features.index_tip_y))
        pitch_norm = inverted_y
        octave_shift = 1.0 if features.middle_tip_y < features.index_tip_y else 0.0
        pitch_freq = norm_to_freq(
            pitch_norm,
            min_freq=pitch_min_freq,
            max_freq=pitch_max_freq,
        )
        freq_with_octave = pitch_freq * (2.0 if octave_shift >= 1.0 else 1.0)
        quantized_pitch = quantize_freq_to_scale(
            freq_with_octave,
            root=pitch_root,
            scale=pitch_scale,
        )
        quantized_freq = quantized_pitch["quantized_freq"]
        final_freq = quantized_freq if quantize_pitch else freq_with_octave
        return [
            ControlEvent(
                "/sample/right/index/y",
                features.index_tip_y,
                {**metadata, "feature": "index_tip_y", "role": "pitch_candidate"},
            ),
            ControlEvent(
                "/sample/right/index/y_inverted",
                inverted_y,
                {
                    **metadata,
                    "feature": "index_tip_y_inverted",
                    "role": "pitch_candidate",
                },
            ),
            ControlEvent(
                "/sample/right/pitch/norm",
                pitch_norm,
                {
                    **metadata,
                    "feature": "pitch_norm",
                    "role": "pitch_candidate",
                },
            ),
            ControlEvent(
                "/sample/right/pitch/octave_shift",
                octave_shift,
                {
                    **metadata,
                    "feature": "middle_above_index",
                    "role": "octave_candidate",
                },
            ),
            ControlEvent(
                "/sample/right/pitch/freq",
                pitch_freq,
                {
                    **metadata,
                    "feature": "pitch_freq",
                    "role": "pitch_candidate",
                    "min_freq": pitch_min_freq,
                    "max_freq": pitch_max_freq,
                },
            ),
            ControlEvent(
                "/sample/right/pitch/freq_with_octave",
                freq_with_octave,
                {
                    **metadata,
                    "feature": "pitch_freq_with_octave",
                    "role": "pitch_candidate",
                    "octave_shift": octave_shift,
                    "base_freq": pitch_freq,
                    "min_freq": pitch_min_freq,
                    "max_freq": pitch_max_freq,
                },
            ),
            ControlEvent(
                "/sample/right/pitch/quantized_freq",
                quantized_freq,
                {
                    **metadata,
                    "feature": "pitch_quantized_freq",
                    "role": "pitch_candidate",
                    "root": quantized_pitch["root"],
                    "scale": quantized_pitch["scale"],
                    "source_freq": freq_with_octave,
                    "quantized_midi": quantized_pitch["quantized_midi"],
                    "quantized_note": quantized_pitch["note_name"],
                },
            ),
            ControlEvent(
                "/sample/right/pitch/final_freq",
                final_freq,
                {
                    **metadata,
                    "feature": "pitch_final_freq",
                    "role": "pitch_candidate",
                    "quantized": quantize_pitch,
                    "root": quantized_pitch["root"],
                    "scale": quantized_pitch["scale"],
                    "source_freq": freq_with_octave,
                    "quantized_freq": quantized_freq,
                    "quantized_note": quantized_pitch["note_name"],
                },
            ),
        ]

    if handedness == "left":
        tone_norm = max(0.0, min(1.0, features.index_tip_x))
        return [
            ControlEvent(
                "/sample/left/pinch",
                features.pinch,
                {**metadata, "feature": "pinch", "role": "amp_candidate"},
            ),
            ControlEvent(
                "/sample/left/tone/norm",
                tone_norm,
                {
                    **metadata,
                    "feature": "index_tip_x",
                    "role": "tone_candidate",
                },
            ),
        ]

    return []


def _safe_float(value, default):
    """Return value as float, falling back for invalid config input."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value, minimum, maximum):
    """Clamp a numeric value to a closed range."""
    return max(minimum, min(maximum, value))


def _sanitize_articulation_settings(
    on_threshold,
    off_threshold,
    hand_loss_release_seconds,
):
    """Return safe tracker settings with a strictly ordered threshold pair."""
    on_threshold = _clamp(
        _safe_float(on_threshold, DEFAULT_ARTICULATION_GATE_ON_THRESHOLD),
        0.0,
        1.0,
    )
    off_threshold = _clamp(
        _safe_float(off_threshold, DEFAULT_ARTICULATION_GATE_OFF_THRESHOLD),
        0.0,
        1.0,
    )
    if on_threshold <= 0.0:
        on_threshold = MIN_ARTICULATION_THRESHOLD_GAP
    if off_threshold >= on_threshold:
        off_threshold = max(
            0.0,
            on_threshold - MIN_ARTICULATION_THRESHOLD_GAP,
        )

    release_seconds = max(
        0.0,
        _safe_float(
            hand_loss_release_seconds,
            DEFAULT_ARTICULATION_HAND_LOSS_RELEASE_SECONDS,
        ),
    )
    return {
        "articulation_gate_on_threshold": on_threshold,
        "articulation_gate_off_threshold": off_threshold,
        "articulation_hand_loss_release_seconds": release_seconds,
    }


def build_articulation_runtime_config(
    threshold,
    hysteresis_width,
    hand_loss_release_ms,
):
    """Convert calibration GUI values into a sanitized runtime config."""
    gate_on = _clamp(
        _safe_float(threshold, DEFAULT_ARTICULATION_GATE_ON_THRESHOLD),
        0.0,
        1.0,
    )
    width = _clamp(
        _safe_float(
            hysteresis_width,
            (
                DEFAULT_ARTICULATION_GATE_ON_THRESHOLD
                - DEFAULT_ARTICULATION_GATE_OFF_THRESHOLD
            ),
        ),
        0.0,
        1.0,
    )
    gate_off = round(max(0.0, gate_on - width), 6)
    release_seconds = max(
        0.0,
        _safe_float(
            hand_loss_release_ms,
            DEFAULT_ARTICULATION_HAND_LOSS_RELEASE_SECONDS * 1000.0,
        )
        / 1000.0,
    )
    return _sanitize_articulation_settings(
        gate_on,
        gate_off,
        release_seconds,
    )


def norm_to_freq(norm, min_freq=DEFAULT_MIN_FREQ, max_freq=DEFAULT_MAX_FREQ):
    """Map a normalized pitch value to frequency using exponential scaling."""
    return _norm_to_freq(norm, min_freq, max_freq)
