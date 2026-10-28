"""Run small smoke tests for platform inputs and outputs.

The default mode verifies OSC connectivity only. Camera smoke testing is
available as a separate mode. Hand tracking smoke testing can display
MediaPipe landmarks, neutral features, and generic events with optional OSC output.
"""

import argparse
from time import sleep

from config import OSC_TARGETS, SAMPLE_MAPPING
from src.mapping import ControlEvent
from src.outputs.osc import OscOutput
from src.pitch import PITCH_GUIDE_MODE_NAMES, SCALE_NAMES


DEFAULT_HAND_MODEL_PATH = "models/hand_landmarker.task"

TEST_STEPS = [
    (0.15, 0.10),
    (0.75, 0.25),
    (0.35, 0.85),
    (0.95, 0.45),
    (0.50, 0.15),
]

STEP_SECONDS = 2.0


def run_osc_smoke_test():
    """Send generic test values to SuperCollider at audible intervals."""
    target = OSC_TARGETS["supercollider"]
    output = OscOutput(target["host"], target["port"])

    print(
        "Sending OSC test values only. "
        "These values are for SuperCollider connectivity probing, not a fixed mapping."
    )

    for index_y, pinch in TEST_STEPS:
        events = [
            ControlEvent("/hand/0/index/y", index_y),
            ControlEvent("/hand/0/pinch", pinch),
        ]

        for event in events:
            output.send(event)
            print(f"sent {event.address} {event.value}")

        sleep(STEP_SECONDS)

    output.close()


def run_camera_smoke_test(camera_index):
    """Show raw webcam video until q is pressed."""
    from src.hand_tracker import OpenCVCameraSmokeTest

    print("Starting camera smoke test. Press q in the preview window to quit.")
    OpenCVCameraSmokeTest(camera_index=camera_index).run()


def run_hands_smoke_test(
    camera_index,
    hand_model_path,
    show_features,
    show_events,
    sample_mapping,
    show_pitch_guides,
    pitch_guide_mode,
    pitch_guide_root,
    pitch_guide_scale,
    show_settings_panel,
    send_osc,
    show_performance_stats,
    performance_stats_interval,
    sample_mapping_config=None,
):
    """Show webcam video with MediaPipe hand landmarks until q is pressed."""
    from src.hand_tracker import MediaPipeHandsSmokeTest

    print(
        "Starting MediaPipe Hands smoke test. "
        "Press q in the preview window to quit."
    )
    if sample_mapping:
        print("Sample handedness-based mapping is enabled.")
    output = None
    event_sink = None
    if send_osc:
        target = OSC_TARGETS["supercollider"]
        output = OscOutput(target["host"], target["port"])
        event_sink = output.send_many
        print(
            "Sending generated ControlEvents over OSC to "
            f"{target['host']}:{target['port']}."
        )

    try:
        MediaPipeHandsSmokeTest(
            camera_index=camera_index,
            model_path=hand_model_path,
            show_features=show_features,
            show_events=show_events,
            sample_mapping=sample_mapping,
            show_pitch_guides=show_pitch_guides,
            pitch_guide_mode=pitch_guide_mode,
            pitch_guide_root=pitch_guide_root,
            pitch_guide_scale=pitch_guide_scale,
            show_settings_panel=show_settings_panel,
            sample_mapping_config=sample_mapping_config,
            event_sink=event_sink,
            show_performance_stats=show_performance_stats,
            performance_stats_interval=performance_stats_interval,
        ).run()
    finally:
        if output is not None:
            output.close()


def parse_args():
    """Parse smoke test selection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        default="osc",
        choices=("osc", "camera", "hands", "ui"),
        help="Smoke test to run. Defaults to the existing OSC test.",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="OpenCV camera index for camera or hands mode.",
    )
    parser.add_argument("--ui-sc-port", type=int, default=57121,
                        help="Regular UI SC language port (legacy hands OSC remains 57120).")
    parser.add_argument(
        "--hand-model-path",
        default=DEFAULT_HAND_MODEL_PATH,
        help="MediaPipe hand landmarker .task model path for hands mode.",
    )
    parser.add_argument(
        "--show-features",
        action="store_true",
        help="Overlay neutral hand feature values in hands mode.",
    )
    parser.add_argument(
        "--show-events",
        action="store_true",
        help="Overlay generic ControlEvent values in hands mode.",
    )
    parser.add_argument(
        "--sample-mapping",
        action="store_true",
        help="Add handedness-based sample musical ControlEvents in hands mode.",
    )
    parser.add_argument(
        "--show-pitch-guides",
        action="store_true",
        help="Overlay sample pitch guide lines in hands mode.",
    )
    parser.add_argument(
        "--pitch-guide-mode",
        choices=PITCH_GUIDE_MODE_NAMES,
        default="simple",
        help="Pitch guide line mode for hands preview.",
    )
    parser.add_argument(
        "--pitch-guide-root",
        default="A",
        help="Root note for chromatic or scale pitch guides.",
    )
    parser.add_argument(
        "--pitch-guide-scale",
        choices=SCALE_NAMES,
        default="minor-pentatonic",
        help="Scale used when --pitch-guide-mode scale is selected.",
    )
    parser.add_argument(
        "--show-settings-panel",
        action="store_true",
        help="Show a prototype OpenCV settings panel in hands mode.",
    )
    parser.add_argument(
        "--quantize-pitch",
        action="store_true",
        help="Emit sample final pitch candidates quantized to the selected scale.",
    )
    parser.add_argument(
        "--pitch-root",
        default="A",
        help="Root note for sample pitch quantization candidates.",
    )
    parser.add_argument(
        "--pitch-scale",
        choices=SCALE_NAMES,
        default="minor-pentatonic",
        help="Scale for sample pitch quantization candidates.",
    )
    parser.add_argument(
        "--pitch-min",
        type=float,
        default=None,
        help="Override sample pitch minimum frequency in Hz.",
    )
    parser.add_argument(
        "--pitch-max",
        type=float,
        default=None,
        help="Override sample pitch maximum frequency in Hz.",
    )
    parser.add_argument(
        "--send-osc",
        action="store_true",
        help="Send generated ControlEvents over OSC in hands mode.",
    )
    parser.add_argument(
        "--show-performance-stats",
        action="store_true",
        help=(
            "Print periodic hands-mode timing stats for capture, MediaPipe, "
            "feature extraction, mapping, OSC, drawing, display, and total "
            "frame time."
        ),
    )
    parser.add_argument(
        "--performance-stats-interval",
        type=float,
        default=1.0,
        help="Seconds between performance stats summaries. Defaults to 1.0.",
    )
    return parser.parse_args()


def build_sample_mapping_config(args):
    """Return sample mapping config with optional CLI overrides applied."""
    sample_mapping_config = dict(SAMPLE_MAPPING)

    if args.pitch_min is not None:
        sample_mapping_config["pitch_min_freq"] = args.pitch_min

    if args.pitch_max is not None:
        sample_mapping_config["pitch_max_freq"] = args.pitch_max

    sample_mapping_config["quantize_pitch"] = args.quantize_pitch
    sample_mapping_config["pitch_root"] = args.pitch_root
    sample_mapping_config["pitch_scale"] = args.pitch_scale

    return sample_mapping_config


def main():
    """Run the selected smoke test."""
    args = parse_args()

    if args.mode == "ui":
        from gui.regular.app import run
        run(args.camera_index, args.hand_model_path, build_sample_mapping_config(args), args.ui_sc_port, args.pitch_guide_mode,
            args.show_performance_stats, args.performance_stats_interval)
        return

    if args.mode == "camera":
        run_camera_smoke_test(args.camera_index)
        return

    if args.mode == "hands":
        run_hands_smoke_test(
            args.camera_index,
            args.hand_model_path,
            args.show_features,
            args.show_events,
            args.sample_mapping,
            args.show_pitch_guides,
            args.pitch_guide_mode,
            args.pitch_guide_root,
            args.pitch_guide_scale,
            args.show_settings_panel,
            args.send_osc,
            args.show_performance_stats,
            args.performance_stats_interval,
            build_sample_mapping_config(args),
        )
        return

    run_osc_smoke_test()


if __name__ == "__main__":
    main()
