import time
import unittest
from unittest.mock import Mock, patch

from app import audio_controller, routine_engine


class RoutineConcurrencyTests(unittest.TestCase):
    def tearDown(self):
        routine_engine.stop_all()
        time.sleep(0.1)

    def test_non_concurrent_routine_blocks_second_start(self):
        with _patched_shutdown():
            first = routine_engine.run_routine(
                [{"type": "wait", "duration": 0.4}],
                routine_id="IN1",
                allow_concurrent=False,
            )
            self.assertTrue(first.is_alive())

            with self.assertRaises(routine_engine.RoutineConcurrencyError):
                routine_engine.run_routine(
                    [{"type": "wait", "duration": 0.1}],
                    routine_id="IN2",
                    allow_concurrent=False,
                )

    def test_concurrent_routines_can_overlap_each_other(self):
        with _patched_shutdown():
            first = routine_engine.run_routine(
                [{"type": "wait", "duration": 0.4}],
                routine_id="IN1",
                allow_concurrent=True,
            )
            second = routine_engine.run_routine(
                [{"type": "wait", "duration": 0.4}],
                routine_id="IN2",
                allow_concurrent=True,
            )

            self.assertTrue(first.is_alive())
            self.assertTrue(second.is_alive())
            active_ids = {run["routine_id"] for run in routine_engine.get_active_runs()}
            self.assertEqual(active_ids, {"IN1", "IN2"})

    def test_non_concurrent_routine_cannot_join_concurrent_active_run(self):
        with _patched_shutdown():
            routine_engine.run_routine(
                [{"type": "wait", "duration": 0.4}],
                routine_id="IN1",
                allow_concurrent=True,
            )

            with self.assertRaises(routine_engine.RoutineConcurrencyError):
                routine_engine.run_routine(
                    [{"type": "wait", "duration": 0.1}],
                    routine_id="IN2",
                    allow_concurrent=False,
                )


class AudioConcurrencyTests(unittest.TestCase):
    def setUp(self):
        audio_controller.MOCK_MODE = True

    def tearDown(self):
        audio_controller.MOCK_MODE = None

    def test_default_sound_stops_existing_audio_first(self):
        fake_path = _FakePath("impact.wav")

        with patch.object(audio_controller, "_safe_audio_path", return_value=fake_path):
            with patch.object(audio_controller, "stop_all_sounds") as stop_all:
                self.assertTrue(audio_controller.play_sound("impact.wav", allow_concurrent=False))

        stop_all.assert_called_once()

    def test_concurrent_sound_does_not_stop_existing_audio(self):
        fake_path = _FakePath("impact.wav")

        with patch.object(audio_controller, "_safe_audio_path", return_value=fake_path):
            with patch.object(audio_controller, "stop_all_sounds") as stop_all:
                self.assertTrue(audio_controller.play_sound("impact.wav", allow_concurrent=True))

        stop_all.assert_not_called()


class _FakePath:
    def __init__(self, name):
        self.name = name

    def exists(self):
        return True


def _patched_shutdown():
    return patch.multiple(
        routine_engine,
        audio_controller=Mock(stop_all_sounds=lambda: None),
        video_controller=Mock(stop_video=lambda: None),
        gpio_controller=Mock(all_off=lambda: None),
    )


if __name__ == "__main__":
    unittest.main()
