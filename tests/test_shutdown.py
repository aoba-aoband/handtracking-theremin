import unittest
from unittest.mock import Mock, patch

from src.hand_tracker import MediaPipeHandsSmokeTest


class ShutdownTests(unittest.TestCase):
    def test_quit_and_camera_failure_both_release_input(self):
        for read_error in (False, True):
            with self.subTest(camera_failure=read_error), patch(
                "src.hand_tracker.cv2.destroyWindow"
            ), patch("src.hand_tracker.cv2.imshow"), patch(
                "src.hand_tracker.cv2.waitKey", return_value=ord("q")
            ), patch("src.hand_tracker.cv2.flip", side_effect=lambda frame, _: frame):
                sink = Mock()
                tracker = MediaPipeHandsSmokeTest(sample_mapping=True, event_sink=sink)
                tracker.start = Mock()
                tracker.capture = Mock()
                tracker.landmarker = Mock()
                capture, landmarker = tracker.capture, tracker.landmarker
                tracker.read = Mock(side_effect=RuntimeError("camera lost")) if read_error else Mock(return_value=Mock())
                for name in ("draw_landmarks", "draw_pitch_guides", "draw_settings_overlay",
                             "draw_articulation_mapping_overlay", "draw_status_overlay", "draw_hand_labels"):
                    setattr(tracker, name, Mock(side_effect=lambda frame, **kwargs: frame))
                if read_error:
                    with self.assertRaisesRegex(RuntimeError, "camera lost"):
                        tracker.run()
                else:
                    tracker.run()
                self.assertEqual(sink.call_args.args[0][0].address, "/sample/panic")
                capture.release.assert_called_once()
                landmarker.close.assert_called_once()

    def test_start_failure_also_cleans_up(self):
        tracker = MediaPipeHandsSmokeTest(sample_mapping=True, event_sink=Mock())
        tracker.start = Mock(side_effect=RuntimeError("startup failed"))
        tracker.capture = Mock()
        capture = tracker.capture
        with patch("src.hand_tracker.cv2.destroyWindow"), self.assertRaises(RuntimeError):
            tracker.run()
        capture.release.assert_called_once()
        tracker.event_sink.assert_called_once()

    def test_transport_failure_does_not_block_cleanup(self):
        tracker = MediaPipeHandsSmokeTest(sample_mapping=True, event_sink=Mock(side_effect=OSError("offline")))
        tracker.capture = Mock()
        capture = tracker.capture
        with patch("src.hand_tracker.cv2.destroyWindow"), self.assertWarns(RuntimeWarning):
            tracker.stop()
        capture.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
