"""Shared effects contracts and patch validation, independent of Qt layouts."""
from copy import deepcopy
import math
from .catalog import Parameter, CATALOG

POST_FX = ("tremolo", "distortion", "fuzz", "delay", "reverb")
FX_NAMES = ("tremolo", "vibrato", "distortion", "fuzz", "delay", "reverb")


def p(key, default, lo=0, hi=1, step=.001, unit="", warp="lin"):
    return Parameter(key, default, lo, hi, step, unit=unit, warp=warp)


def toggle(): return Parameter("on", 0, step=1, kind="toggle")
def wave(): return Parameter("wave", 0, 0, 2, 1, kind="choice", choices=("Sine", "Triangle", "Square"))


FX_SPECS = {
    "tremolo": {s.key: s for s in (toggle(), p("rate", 5, .05, 60, .01, "Hz", "exp"), p("depth", .5, 0, 2), wave())},
    "vibrato": {s.key: s for s in (toggle(), p("rate", 5, .05, 60, .01, "Hz", "exp"), p("depth", 20, 0, 400, .1, "ct"), wave())},
    "distortion": {s.key: s for s in (toggle(), p("drive", 2, 1, 80, .01, warp="exp"), p("tone", 8000, 100, 18000, 1, "Hz", "exp"), p("level", .5, 0, 2), p("mix", 1))},
    "fuzz": {s.key: s for s in (toggle(), p("drive", 8, 1, 160, .01, warp="exp"), p("tone", 4000, 100, 18000, 1, "Hz", "exp"), p("level", .4, 0, 2), p("mix", 1))},
}
LEGACY_FX = {}
for effect, prefix in (("delay", "delay"), ("reverb", "reverb")):
    FX_SPECS[effect] = {}
    for old_key, spec in CATALOG["basic"].items():
        if old_key.startswith(prefix):
            key = old_key[len(prefix):]
            key = key[0].lower() + key[1:]
            from dataclasses import replace
            FX_SPECS[effect][key] = replace(spec, key=key)
            LEGACY_FX[old_key] = (effect, key)

TARGETS = {"tremolo": ("depth", "rate"), "vibrato": ("depth", "rate"),
           "distortion": ("drive",), "fuzz": ("drive",), "delay": ("mix",), "reverb": ("mix",)}


def mapping_defaults(effect):
    return {"source": "manual", "target": TARGETS[effect][0], "zero": 90., "maximum": 0.,
            "direction": "shortest", "fold": False, "threshold": .02, "invert": False,
            "smoothing": .1, "deadband": 1., "min_separation": 12., "curve": "linear", "bend": 2.}


def initial_effects():
    return {"values": {fx: {k: s.default for k, s in specs.items()} for fx, specs in FX_SPECS.items()},
            "mappings": {fx: mapping_defaults(fx) for fx in FX_NAMES},
            "keys": {fx: {"key": "", "mode": "toggle"} for fx in FX_NAMES}, "order": list(POST_FX)}


def finite(value, lo, hi, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{name}: expected {lo}..{hi}")
    return float(value)


def validate_effects(data):
    clean = initial_effects()
    if not isinstance(data, dict) or set(data) != set(clean): raise ValueError("Unknown or missing Effects section")
    for section in ("values", "mappings", "keys"):
        if set(data[section]) != set(FX_NAMES): raise ValueError(f"Invalid Effects {section}")
    seen = set()
    for fx in FX_NAMES:
        if set(data["values"][fx]) != set(FX_SPECS[fx]): raise ValueError(f"Unknown {fx} parameter")
        clean["values"][fx] = {k: FX_SPECS[fx][k].validate(v) for k, v in data["values"][fx].items()}
        mapping = deepcopy(data["mappings"][fx])
        if set(mapping) != set(clean["mappings"][fx]): raise ValueError(f"Invalid {fx} mapping fields")
        for key, choices in (("source", ("manual", "left", "right")), ("target", TARGETS[fx]),
                             ("direction", ("shortest", "clockwise", "counterclockwise")),
                             ("curve", ("linear", "slow", "fast"))):
            if mapping[key] not in choices: raise ValueError(f"Unknown {fx} {key}")
        for key, lo, hi in (("zero", -180, 180), ("maximum", -180, 180), ("threshold", 0, .99),
                            ("smoothing", .005, 2), ("deadband", 0, 15), ("min_separation", 2, 100), ("bend", 1, 8)):
            mapping[key] = finite(mapping[key], lo, hi, key)
        for key in ("fold", "invert"):
            if type(mapping[key]) is not bool: raise ValueError(f"{key} must be a boolean")
        period = 180 if mapping["fold"] else 360
        if abs((mapping["maximum"] - mapping["zero"]) % period) < .001:
            raise ValueError("Zero and maximum must define a nonzero angle range")
        clean["mappings"][fx] = mapping
        keys = data["keys"][fx]
        if not isinstance(keys, dict) or set(keys) != {"key", "mode"} or keys["mode"] not in ("toggle", "hold") or not isinstance(keys["key"], str):
            raise ValueError("Invalid key binding")
        from PySide6.QtGui import QKeySequence
        sequence = QKeySequence.fromString(keys["key"], QKeySequence.SequenceFormat.PortableText)
        canonical = sequence.toString(QKeySequence.SequenceFormat.PortableText)
        if keys["key"] and (sequence.count() != 1 or not canonical): raise ValueError("Use a single key or key combination")
        if canonical in ("F5", "F6", "F12") or canonical in seen: raise ValueError("Duplicate or reserved key: " + canonical)
        if canonical: seen.add(canonical)
        clean["keys"][fx] = {"key": canonical, "mode": keys["mode"]}
    if not isinstance(data["order"], list) or len(data["order"]) != len(POST_FX) or set(data["order"]) != set(POST_FX):
        raise ValueError("FX order must contain each post-source effect once (vibrato is source-side)")
    clean["order"] = list(data["order"])
    return clean


def sync_legacy_values(settings):
    for old, (fx, key) in LEGACY_FX.items():
        settings["probes"]["basic"][old] = settings["effects"]["values"][fx][key]
