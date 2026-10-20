"""Regenerate SC bridge validation ranges from the source ControlSpecs."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui.regular.catalog import CATALOG, ROOT


def generate():
    lines = ["// Generated from SC ControlSpecs by tools/generate_regular_specs.py.", "("]
    for probe, specs in CATALOG.items():
        lines.append(probe + ": (")
        for key, spec in specs.items():
            if spec.kind != "readout":
                lines.append(f"    {key}: [{spec.minimum}, {spec.maximum}, {spec.step}],")
        lines.append("),")
    lines.append(")")
    return "\n".join(lines)


if __name__ == "__main__":
    (ROOT / "sc/regular_specs.scd").write_text(generate(), encoding="utf-8")
