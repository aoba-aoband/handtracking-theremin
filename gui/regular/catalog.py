"""Read parameter contracts from the actual SC probes, never from mockups."""
from dataclasses import dataclass
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {"basic": "basic_receiver.scd", "subtractive": "subtractive_probe.scd"}


@dataclass(frozen=True)
class Parameter:
    key: str
    default: float
    minimum: float = 0
    maximum: float = 1
    step: float = .001
    warp: str = "lin"
    kind: str = "range"
    unit: str = ""
    choices: tuple = ()

    def validate(self, value):
        import math
        value = float(value)
        if not math.isfinite(value) or not self.minimum <= value <= self.maximum:
            raise ValueError(f"{self.key}: expected {self.minimum}..{self.maximum}")
        if self.kind in ("toggle", "choice") and value != int(value):
            raise ValueError(f"{self.key}: expected an integer")
        if self.kind == "readout":
            raise ValueError(f"{self.key} is read-only")
        # ControlSpec steps are absolute, not percentages of the slider.
        if self.step:
            value = round(value / self.step) * self.step
        return min(self.maximum, max(self.minimum, value))


GROUPS = {
    "basic": [
        ("Additive", "additiveOn additiveMix additiveGain"),
        ("Harmonics", " ".join(f"harmonic{i}" for i in range(1, 13))),
        ("Response", "freqLag ampLag"),
        ("Performance / Output", "performanceGate crescendoTime decrescendoTime outputLevel ampMin ampMax"),
        ("Portamento", "portamentoOn portamentoTime"),
        ("Soft Clip", "softClipOn softClipDrive softClipMix"),
        ("Filter", "filterOn filterCutoff filterRq filterMix filterLag"),
        ("Delay", "delayOn delayMix delayTime delayFeedback delayFilterCutoff delayFilterRq delayLag"),
        ("Reverb", "reverbOn reverbMix reverbRoom reverbDamp"),
        ("Monitor", "monitorOn monitorRate"),
    ],
    "subtractive": [
        ("Osc 1", "osc1Wave"),
        ("Osc 2", "osc2On osc2Wave osc2Octave osc2DetuneCents"),
        ("Source Mix", "oscMix pulseWidth subMix noiseMix"),
        ("Response", "freqLag ampAttack ampRelease"),
        ("Performance / Output", "performanceGate crescendoTime decrescendoTime outputLevel ampMin ampMax"),
        ("Articulation", "articulationOn articulationGate articulationAttack articulationRelease"),
        ("Filter", "filterOn filterCutoff filterRq filterMix filterLag keyTracking"),
        ("Filter Env", "filterEnvOn filterEnvAttack filterEnvDecay filterEnvSustain filterEnvRelease filterEnvAmountOctaves"),
        ("Hand Tone", "handToneOn toneMinCutoff toneMaxCutoff toneInvert handToneCutoff"),
        ("Monitor", "monitorOn monitorRate"),
    ],
}

LABELS = {
    "freqLag": "Freq Lag", "ampLag": "Amp Lag", "ampAttack": "Amp Attack", "ampRelease": "Amp Release",
    "crescendoTime": "Crescendo", "decrescendoTime": "Decrescendo", "outputLevel": "Output Level",
    "performanceGate": "Gate", "ampMin": "Amp Min", "ampMax": "Amp Max",
    "oscMix": "Osc Mix", "pulseWidth": "Pulse Width", "subMix": "Sub Mix", "noiseMix": "Noise Mix",
    "toneMinCutoff": "Min Cutoff", "toneMaxCutoff": "Max Cutoff", "toneInvert": "Invert",
    "handToneCutoff": "Hand Cutoff", "articulationGate": "Gate (tracker)", "keyTracking": "Key Tracking",
    "delayFilterCutoff": "Filter Cutoff", "delayFilterRq": "Filter Rq", "handToneOn": "On",
    "monitorRate": "Rate", "filterEnvAmountOctaves": "Amount", "osc2DetuneCents": "Detune",
}


def label(key):
    if key in LABELS:
        return LABELS[key]
    for prefix in ("filterEnv", "articulation", "portamento", "softClip", "additive", "filter", "delay", "reverb", "monitor", "osc1", "osc2"):
        if key.startswith(prefix):
            return key[len(prefix):] or key
    return key


def catalog():
    result = {}
    number = r"(-?\d+(?:\.\d+)?)"
    for probe, filename in SOURCES.items():
        text = (ROOT / "sc" / filename).read_text(encoding="utf-8")
        defaults_text = re.search(r"~\w+Defaults = \((.*?)\n\s*\);", text, re.S).group(1)
        defaults = {k: float(v) for k, v in re.findall(r"(\w+):\s*" + number, defaults_text)}
        specs = {}
        pattern = r'~make\w+Slider\.\("[^"]+",\s*\\(\w+),\s*' + number + r",\s*" + number + r",\s*" + number + r"(?:,\s*\\(\w+))?\)"
        for key, lo, hi, step, warp in re.findall(pattern, text):
            unit = "Hz" if "Cutoff" in key else "s" if any(x in key.lower() for x in ("time", "lag", "attack", "decay", "release")) else ""
            if key == "osc2DetuneCents":
                unit = "ct"
            if key in ("osc2Octave", "filterEnvAmountOctaves"):
                unit = "oct"
            specs[key] = Parameter(key, defaults[key], float(lo), float(hi), float(step), warp or "lin", unit=unit)
        toggles = set(re.findall(r'~make\w+Toggle\.\("[^"]+",\s*\\(\w+)\)', text))
        toggles |= {"performanceGate", "monitorOn"}
        if probe == "subtractive":
            toggles.add("toneInvert")
            for key in ("osc1Wave", "osc2Wave"):
                specs[key] = Parameter(key, defaults[key], 0, 2, 1, kind="choice", choices=("Saw", "Pulse", "Triangle"))
            for key in ("toneMinCutoff", "toneMaxCutoff"):
                specs[key] = Parameter(key, defaults[key], 40, 16000, 1, "exp", unit="Hz")
            specs["handToneCutoff"] = Parameter("handToneCutoff", defaults["handToneCutoff"], 40, 16000, 1, kind="readout", unit="Hz")
            specs["articulationGate"] = Parameter("articulationGate", 0, step=1, kind="readout")
        for key in toggles:
            specs[key] = Parameter(key, defaults[key], step=1, kind="toggle")
        specs["monitorRate"] = Parameter("monitorRate", defaults["monitorRate"], .1, 30, .1, unit="Hz")
        missing = set(defaults) - set(specs)
        if missing:
            raise ValueError(f"Uncatalogued SC parameters: {probe}: {sorted(missing)}")
        ordered = {key: specs[key] for _, keys in GROUPS[probe] for key in keys.split()}
        if set(ordered) != set(defaults):
            raise ValueError(f"Module registry differs from {filename}")
        result[probe] = ordered
    return result


CATALOG = catalog()
