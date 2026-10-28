"""Mirror-aware screen angle and stateful mapping, independent of widgets/OSC."""
import math


def pinch_angle(features, width, height, minimum_pixels=12):
    if features is None or width <= 0 or height <= 0: return None
    # Thumb -> index, mirrored display: x right, y up. 0=right, 90=up.
    dx = (features.thumb_tip_x - features.index_tip_x) * width
    dy = (features.thumb_tip_y - features.index_tip_y) * height
    if not all(math.isfinite(v) for v in (dx, dy)) or math.hypot(dx, dy) < minimum_pixels: return None
    return math.degrees(math.atan2(dy, dx))


def angle_normalized(angle, config):
    period = 180 if config["fold"] else 360
    start, end = config["zero"], config["maximum"]
    delta = (end - start) % period
    if config["direction"] == "clockwise": delta = delta - period
    elif config["direction"] == "shortest" and delta > period / 2: delta -= period
    if abs(delta) < .001: return 0.
    lo, hi = min(0., delta), max(0., delta)
    candidates = [angle - start + k * period for k in range(-3, 4)]
    distance = lambda x: max(lo - x, 0., x - hi)
    unwrapped = min(candidates, key=lambda x: (distance(x), abs(x)))
    value = min(1., max(0., unwrapped / delta))
    return response_curve(value, config)


def response_curve(value, config):
    if config["invert"]: value = 1 - value
    threshold = config["threshold"]
    value = max(0., min(1., (value - threshold) / (1 - threshold)))
    if config["curve"] == "slow": value = value ** config["bend"]
    elif config["curve"] == "fast": value = 1 - (1 - value) ** config["bend"]
    return value


class AngleMapper:
    def __init__(self): self.states = {}

    def update(self, effect, features, width, height, config, dt):
        state = self.states.setdefault(effect, {"angle": None, "value": 0., "presence": 0.})
        angle = pinch_angle(features, width, height, config["min_separation"])
        valid = angle is not None
        if valid:
            difference = abs(((angle - (state["angle"] if state["angle"] is not None else angle) + 180) % 360) - 180)
            if state["angle"] is None or difference >= config["deadband"]: state["angle"] = angle
            target = angle_normalized(state["angle"], config)
        else:
            target = 0.
            state["angle"] = None
        alpha = -math.expm1(-max(0., min(dt, .25)) / config["smoothing"])
        state["value"] += (target - state["value"]) * alpha
        state["presence"] += ((1. if valid else 0.) - state["presence"]) * alpha
        return {"angle": angle, "valid": valid, "normalized": state["value"], "presence": state["presence"]}
