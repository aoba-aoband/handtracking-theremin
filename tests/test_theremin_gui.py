import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from gui.theremin_gui import DEFAULTS, generate_script


class ThereminCompatibilityTests(unittest.TestCase):
    def test_generated_player_handles_tasks_landmarks_and_releases_resources(self):
        from mediapipe.tasks.python.components.containers.landmark import NormalizedLandmark

        code = compile(generate_script(DEFAULTS), "generated_theremin.py", "exec")
        result = Mock(hand_landmarks=[
            [NormalizedLandmark(x=x, y=0.4) for _ in range(21)] for x in (0.25, 0.75)
        ])
        hands = Mock()
        hands.detect_for_video.return_value = result
        capture = Mock()
        capture.read.return_value = (True, np.zeros((240, 320, 3), dtype=np.uint8))
        stream = Mock()
        with patch.object(vision.HandLandmarker, "create_from_options", return_value=hands), patch(
            "cv2.VideoCapture", return_value=capture
        ), patch("cv2.imshow"), patch("cv2.waitKey", return_value=ord("q")), patch(
            "cv2.destroyAllWindows"
        ), patch("sounddevice.OutputStream", return_value=stream):
            exec(code, {})
        hands.detect_for_video.assert_called_once()
        hands.close.assert_called_once()
        stream.close.assert_called_once()
        capture.release.assert_called_once()

    def test_bundled_model_initializes_current_tasks_api(self):
        model = Path(__file__).resolve().parents[1] / "models/hand_landmarker.task"
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
        )
        import mediapipe as mp
        with vision.HandLandmarker.create_from_options(options) as hands:
            result = hands.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((240, 320, 3), dtype=np.uint8)), 1
            )
        self.assertEqual(result.hand_landmarks, [])

    def test_invalid_custom_scale_is_rejected_before_launch(self):
        for scale in ("", "abc"):
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                generate_script({**DEFAULTS, "scale_name": "Custom", "custom_pcs": scale})


if __name__ == "__main__":
    unittest.main()
