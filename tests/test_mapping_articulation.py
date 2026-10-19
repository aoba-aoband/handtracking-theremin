import unittest

from src.features import HandFeatures
from src.mapping import (
    ARTICULATION_GATE_ADDRESS,
    LeftArticulationGateTracker,
    SampleMusicalMapper,
    build_articulation_runtime_config,
)


class FakeClock:
    def __init__(self, start=100.0):
        self.value = start

    def monotonic(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def make_hand(handedness, pinch=0.0, index_x=0.25, index_y=0.5):
    return HandFeatures(
        handedness=handedness,
        index_tip_x=index_x,
        index_tip_y=index_y,
        middle_tip_x=index_x,
        middle_tip_y=index_y + 0.1,
        thumb_tip_x=index_x,
        thumb_tip_y=index_y,
        pinch=pinch,
        landmarks_count=21,
    )


def event_by_address(events, address):
    matches = [event for event in events if event.address == address]
    if not matches:
        raise AssertionError(f"Missing event {address!r}")
    return matches[-1]


class SampleMappingArticulationTests(unittest.TestCase):
    def make_mapper(self, clock):
        return SampleMusicalMapper(
            mapping_config={
                "articulation_gate_on_threshold": 0.65,
                "articulation_gate_off_threshold": 0.45,
                "articulation_hand_loss_release_seconds": 0.25,
            },
            clock=clock.monotonic,
        )

    def test_gate_turns_on_at_on_threshold(self):
        clock = FakeClock()
        mapper = self.make_mapper(clock)

        events = mapper.map([make_hand("Left", pinch=0.65)])
        gate_event = event_by_address(events, ARTICULATION_GATE_ADDRESS)

        self.assertEqual(gate_event.value, 1)
        self.assertEqual(gate_event.metadata["feature"], "pinch")
        self.assertEqual(gate_event.metadata["role"], "articulation_gate")
        self.assertEqual(gate_event.metadata["gate_on_threshold"], 0.65)
        self.assertEqual(gate_event.metadata["gate_off_threshold"], 0.45)

    def test_gate_holds_on_between_thresholds(self):
        clock = FakeClock()
        mapper = self.make_mapper(clock)

        mapper.map([make_hand("Left", pinch=0.8)])
        events = mapper.map([make_hand("Left", pinch=0.55)])

        self.assertEqual(event_by_address(events, ARTICULATION_GATE_ADDRESS).value, 1)

    def test_gate_turns_off_at_off_threshold(self):
        clock = FakeClock()
        mapper = self.make_mapper(clock)

        mapper.map([make_hand("Left", pinch=0.8)])
        events = mapper.map([make_hand("Left", pinch=0.45)])

        self.assertEqual(event_by_address(events, ARTICULATION_GATE_ADDRESS).value, 0)

    def test_gate_holds_off_between_thresholds(self):
        clock = FakeClock()
        mapper = self.make_mapper(clock)

        events = mapper.map([make_hand("Left", pinch=0.55)])

        self.assertEqual(event_by_address(events, ARTICULATION_GATE_ADDRESS).value, 0)

    def test_hand_loss_does_not_release_before_timeout(self):
        clock = FakeClock()
        mapper = self.make_mapper(clock)

        mapper.map([make_hand("Left", pinch=0.8)])
        clock.advance(0.1)
        events = mapper.map([])

        self.assertNotIn(ARTICULATION_GATE_ADDRESS, [event.address for event in events])

    def test_hand_loss_repeats_release_after_timeout(self):
        clock = FakeClock()
        mapper = self.make_mapper(clock)

        mapper.map([make_hand("Left", pinch=0.8)])
        clock.advance(0.3)
        events = mapper.map([])
        gate_event = event_by_address(events, ARTICULATION_GATE_ADDRESS)

        self.assertEqual(gate_event.value, 0)
        self.assertEqual(gate_event.metadata["reason"], "left_hand_loss_timeout")
        self.assertEqual(
            event_by_address(mapper.map([]), ARTICULATION_GATE_ADDRESS).value,
            0,
        )

    def test_existing_sample_events_are_preserved(self):
        clock = FakeClock()
        mapper = self.make_mapper(clock)

        events = mapper.map(
            [
                make_hand("Left", pinch=0.7, index_x=0.33),
                make_hand("Right", pinch=0.1, index_y=0.25),
            ]
        )
        addresses = {event.address for event in events}

        self.assertIn("/sample/left/pinch", addresses)
        self.assertIn("/sample/left/tone/norm", addresses)
        self.assertIn("/sample/right/pitch/final_freq", addresses)
        self.assertIn(ARTICULATION_GATE_ADDRESS, addresses)
        self.assertEqual(event_by_address(events, "/sample/left/pinch").value, 0.7)
        self.assertEqual(event_by_address(events, "/sample/left/tone/norm").value, 0.33)

    def test_invalid_config_is_sanitized(self):
        tracker = LeftArticulationGateTracker(
            mapping_config={
                "articulation_gate_on_threshold": 0.2,
                "articulation_gate_off_threshold": 0.9,
                "articulation_hand_loss_release_seconds": -1,
            },
            clock=FakeClock().monotonic,
        )

        self.assertGreater(tracker.on_threshold, tracker.off_threshold)
        self.assertGreaterEqual(tracker.off_threshold, 0.0)
        self.assertLessEqual(tracker.on_threshold, 1.0)
        self.assertGreaterEqual(tracker.hand_loss_release_seconds, 0.0)

    def test_runtime_thresholds_are_applied_with_hysteresis(self):
        clock = FakeClock()
        mapper = self.make_mapper(clock)
        runtime_config = build_articulation_runtime_config(0.3, 0.1, 250)

        mapper.update_articulation_settings(runtime_config)
        on_events = mapper.map([make_hand("Left", pinch=0.3)])
        held_events = mapper.map([make_hand("Left", pinch=0.25)])
        off_events = mapper.map([make_hand("Left", pinch=0.2)])

        self.assertAlmostEqual(
            mapper.articulation_tracker.on_threshold,
            0.3,
        )
        self.assertAlmostEqual(
            mapper.articulation_tracker.off_threshold,
            0.2,
        )
        self.assertEqual(
            event_by_address(on_events, ARTICULATION_GATE_ADDRESS).value,
            1,
        )
        self.assertEqual(
            event_by_address(held_events, ARTICULATION_GATE_ADDRESS).value,
            1,
        )
        self.assertEqual(
            event_by_address(off_events, ARTICULATION_GATE_ADDRESS).value,
            0,
        )

    def test_hysteresis_wider_than_threshold_clips_gate_off_to_zero(self):
        runtime_config = build_articulation_runtime_config(0.3, 0.8, 250)

        self.assertAlmostEqual(
            runtime_config["articulation_gate_on_threshold"],
            0.3,
        )
        self.assertEqual(
            runtime_config["articulation_gate_off_threshold"],
            0.0,
        )

    def test_runtime_update_preserves_current_gate_state(self):
        clock = FakeClock()
        mapper = self.make_mapper(clock)
        mapper.map([make_hand("Left", pinch=0.8)])

        runtime_config = build_articulation_runtime_config(0.9, 0.1, 250)
        mapper.update_articulation_settings(runtime_config)
        events = mapper.map([make_hand("Left", pinch=0.85)])

        self.assertEqual(mapper.articulation_tracker.gate, 1)
        self.assertEqual(
            event_by_address(events, ARTICULATION_GATE_ADDRESS).value,
            1,
        )

    def test_runtime_timeout_update_preserves_last_seen_time(self):
        clock = FakeClock()
        mapper = self.make_mapper(clock)
        mapper.map([make_hand("Left", pinch=0.8)])

        runtime_config = build_articulation_runtime_config(0.65, 0.2, 500)
        mapper.update_articulation_settings(runtime_config)
        clock.advance(0.3)
        self.assertNotIn(
            ARTICULATION_GATE_ADDRESS,
            [event.address for event in mapper.map([])],
        )

        clock.advance(0.21)
        events = mapper.map([])
        self.assertEqual(
            event_by_address(events, ARTICULATION_GATE_ADDRESS).value,
            0,
        )


if __name__ == "__main__":
    unittest.main()
