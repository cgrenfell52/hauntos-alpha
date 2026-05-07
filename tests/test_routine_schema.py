import unittest

from app import config_store, routine_schema


class RoutineSchemaTests(unittest.TestCase):
    def test_normalize_routines_adds_sound_concurrency_default(self):
        routines = {
            "IN1": [{"type": "sound", "file": "thunder.wav", "mode": "play_and_continue"}],
            "IN2": [],
            "IN3": [],
            "IN4": [],
        }

        normalized = routine_schema.normalize_routines(routines, config_store.DEFAULT_DEVICES)

        self.assertFalse(normalized["IN1"][0]["allow_concurrent"])

    def test_rejects_unknown_output_target(self):
        routines = {
            "IN1": [{"type": "output", "target": "OUT9", "action": "on"}],
            "IN2": [],
            "IN3": [],
            "IN4": [],
        }

        with self.assertRaisesRegex(ValueError, "OUT9"):
            routine_schema.validate_routines(routines, config_store.DEFAULT_DEVICES)

    def test_rejects_unsafe_media_filename(self):
        routines = {
            "IN1": [{"type": "sound", "file": "../escape.wav", "mode": "play_and_continue"}],
            "IN2": [],
            "IN3": [],
            "IN4": [],
        }

        with self.assertRaisesRegex(ValueError, "filename"):
            routine_schema.validate_routines(routines, config_store.DEFAULT_DEVICES)

    def test_rejects_non_boolean_concurrency_flag(self):
        routines = {
            "IN1": [{"type": "sound", "file": "thunder.wav", "allow_concurrent": "yes"}],
            "IN2": [],
            "IN3": [],
            "IN4": [],
        }

        with self.assertRaisesRegex(ValueError, "allow_concurrent"):
            routine_schema.validate_routines(routines, config_store.DEFAULT_DEVICES)


if __name__ == "__main__":
    unittest.main()
