"""Validated settings and independent patch/layout persistence."""
from copy import deepcopy
import json
import math
from pathlib import Path

from config import SAMPLE_MAPPING
from src.pitch import NOTE_NAMES, SCALE_NAMES, PITCH_GUIDE_MODE_NAMES, midi_to_freq
from .catalog import CATALOG
from .effects import initial_effects, validate_effects, LEGACY_FX, sync_legacy_values


def initial_settings():
    return {
        "schema_version": 2,
        "migration": None,
        "effects": initial_effects(),
        "probe": "basic",
        "probes": {p: {k: s.default for k, s in specs.items() if s.kind != "readout"} for p, specs in CATALOG.items()},
        "mapping": {**SAMPLE_MAPPING, "pitch_root": "A", "pitch_scale": "minor-pentatonic", "quantize_pitch": False},
        "guide_mode": "simple",
    }


def validate_settings(data):
    clean = initial_settings()
    if not isinstance(data, dict) or set(data) - set(clean):
        raise ValueError("Unknown patch fields")
    version = data.get("schema_version", 1)
    if type(version) is not int or version not in (1, 2): raise ValueError("Unsupported patch schema")
    if data.get("probe") not in CATALOG:
        raise ValueError("Unknown probe")
    if not isinstance(data.get("probes"), dict) or set(data["probes"]) != set(CATALOG):
        raise ValueError("Unknown or missing probe banks")
    clean["probe"] = data["probe"]
    for p, specs in CATALOG.items():
        for key, value in data["probes"][p].items():
            if key not in specs or specs[key].kind == "readout":
                raise ValueError(f"Unknown or read-only parameter: {key}")
            clean["probes"][p][key] = specs[key].validate(value)
        # A patch must never turn on performance gate.
        clean["probes"][p]["performanceGate"] = 0
        vals = clean["probes"][p]
        if p == "subtractive" and vals["toneMinCutoff"] > vals["toneMaxCutoff"]:
            raise ValueError("Hand Tone Min Cutoff must not exceed Max Cutoff")
    mapping = deepcopy(data["mapping"])
    if set(mapping) != set(clean["mapping"]): raise ValueError("Unknown or missing mapping fields")
    lo, hi = mapping["pitch_min_freq"], mapping["pitch_max_freq"]
    if not midi_to_freq(0) <= lo < hi <= midi_to_freq(127):
        raise ValueError("Pitch Min must be below Max (MIDI 0–127)")
    if mapping["pitch_root"] not in NOTE_NAMES or mapping["pitch_scale"] not in SCALE_NAMES:
        raise ValueError("Unknown root or scale")
    if type(mapping["quantize_pitch"]) is not bool:
        raise ValueError("Quantize must be ON or OFF")
    on, off = mapping["articulation_gate_on_threshold"], mapping["articulation_gate_off_threshold"]
    release = mapping["articulation_hand_loss_release_seconds"]
    if not 0 <= off < on <= 1 or not math.isfinite(release) or not 0 <= release <= 2:
        raise ValueError("Invalid articulation calibration")
    if data["guide_mode"] not in PITCH_GUIDE_MODE_NAMES:
        raise ValueError("Unknown guide mode")
    clean["mapping"] = {k: mapping[k] for k in clean["mapping"]}
    clean["guide_mode"] = data["guide_mode"]
    if version == 1:
        original_fx = {key: clean["probes"]["basic"][key] for key in LEGACY_FX}
        for old, (fx, key) in LEGACY_FX.items():
            clean["effects"]["values"][fx][key] = clean["probes"]["basic"][old]
        if clean["probe"] == "subtractive":
            for fx in ("delay", "reverb"): clean["effects"]["values"][fx]["on"] = 0
        clean["migration"] = {"from_version": 1, "basic_fx": original_fx}
    else:
        clean["effects"] = validate_effects(data["effects"])
        migration = data.get("migration")
        if migration is not None:
            if not isinstance(migration, dict) or set(migration) != {"from_version", "basic_fx"} or migration["from_version"] != 1 or set(migration["basic_fx"]) != set(LEGACY_FX):
                raise ValueError("Invalid legacy migration metadata")
            clean["migration"] = {"from_version": 1, "basic_fx": {key: CATALOG["basic"][key].validate(value) for key, value in migration["basic_fx"].items()}}
    sync_legacy_values(clean)
    return clean


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory or Path(__file__).resolve().parents[2] / "user_data")

    def write(self, category, name, payload):
        if category not in ("patches", "layouts") or not name.strip() or any(c in name for c in '<>:"/\\|?*') or name in (".", ".."):
            raise ValueError("Enter a valid file name")
        directory = self.directory / category
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (name.strip() + ".json")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 2 if category == "patches" else 1, "kind": category, "data": payload}, indent=2), encoding="utf-8")
        tmp.replace(path)

    def read(self, category, name):
        path = self.directory / category / (name + ".json")
        # Name validation also protects paths supplied by a corrupt menu/session.
        if path.resolve().parent != (self.directory / category).resolve():
            raise ValueError("Invalid saved name")
        content = json.loads(path.read_text(encoding="utf-8"))
        if content["version"] not in ((1, 2) if category == "patches" else (1,)) or content["kind"] != category:
            raise ValueError("Unsupported file format")
        return content["data"]

    def names(self, category):
        return sorted(p.stem for p in (self.directory / category).glob("*.json"))
