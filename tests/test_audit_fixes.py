import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from app import audio_controller, config_store, gpio_controller, scheduler, video_controller
from app.routes import register_routes


ROOT = Path(__file__).resolve().parents[1]


def build_test_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    register_routes(app)
    return app


class AuditFixTests(unittest.TestCase):
    def test_mutating_apis_require_operator_login(self):
        app = build_test_app()
        settings = {
            "setup_complete": True,
            "mock_mode": True,
            "active_low_outputs": False,
            "active_low_inputs": True,
            "show_armed": False,
        }

        with (
            patch("app.routes.config_store.get_settings", return_value=settings),
            patch("app.routes.config_store.save_settings"),
            patch("app.routes.routine_engine.stop_all"),
        ):
            client = app.test_client()

            unauthenticated = client.post("/api/stop")
            self.assertEqual(unauthenticated.status_code, 401)

            login = client.post("/api/auth/login", json={"pin": "1031"})
            self.assertEqual(login.status_code, 200)

            authenticated = client.post("/api/stop")
            self.assertEqual(authenticated.status_code, 200)

    def test_dashboard_redirects_to_login_when_operator_is_not_authenticated(self):
        app = build_test_app()
        settings = {
            "setup_complete": True,
            "mock_mode": True,
            "active_low_outputs": False,
            "active_low_inputs": True,
        }

        with patch("app.routes.config_store.get_settings", return_value=settings):
            response = app.test_client().get("/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_read_apis_require_login_after_setup_except_safe_status(self):
        app = build_test_app()
        settings = {
            "setup_complete": True,
            "mock_mode": True,
            "active_low_outputs": False,
            "active_low_inputs": True,
            "operator_pin_hash": "private-hash",
        }

        with (
            patch("app.routes.config_store.get_settings", return_value=settings),
            patch("app.routes.config_store.get_devices", return_value=config_store._default_for("devices")),
            patch("app.routes.routine_engine.get_runtime_status", return_value={}),
            patch("app.routes.routine_engine.get_active_runs", return_value=[]),
            patch("app.routes.routine_engine.is_running", return_value=False),
            patch("app.routes.gpio_controller.get_output_states", return_value={}),
        ):
            client = app.test_client()
            devices_response = client.get("/api/devices")
            status_response = client.get("/api/status")

        self.assertEqual(devices_response.status_code, 401)
        self.assertEqual(status_response.status_code, 200)
        self.assertNotIn("operator_pin_hash", status_response.get_json()["settings"])

    def test_manual_pulse_is_interrupted_by_all_off(self):
        gpio_controller.MOCK_MODE = True
        gpio_controller.SETUP_COMPLETE = True
        gpio_controller.DEVICES = config_store._default_for("devices")
        gpio_controller.OUTPUT_STATES = {"OUT1": False}

        worker = threading.Thread(target=lambda: gpio_controller.pulse("OUT1", 5), daemon=True)
        worker.start()

        deadline = time.monotonic() + 1
        while not gpio_controller.OUTPUT_STATES.get("OUT1") and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertTrue(gpio_controller.OUTPUT_STATES["OUT1"])
        gpio_controller.all_off()
        worker.join(timeout=0.5)

        self.assertFalse(worker.is_alive())
        self.assertFalse(gpio_controller.OUTPUT_STATES["OUT1"])

    def test_output_pulse_duration_is_capped(self):
        app = build_test_app()
        settings = {
            "setup_complete": True,
            "mock_mode": True,
            "active_low_outputs": False,
            "active_low_inputs": True,
        }

        with (
            patch("app.routes.config_store.get_settings", return_value=settings),
            patch("app.routes.gpio_controller.pulse"),
        ):
            client = app.test_client()
            with client.session_transaction() as session:
                session["operator_authenticated"] = True

            response = client.post("/api/output/OUT1/pulse", json={"duration": 31})

        self.assertEqual(response.status_code, 400)
        self.assertIn("30 seconds or less", response.get_json()["error"])

    def test_setup_save_resets_audio_and_video_mock_mode_cache(self):
        app = build_test_app()
        devices = config_store._default_for("devices")
        settings = config_store._default_for("settings")
        settings["setup_complete"] = True
        audio_controller.MOCK_MODE = True
        video_controller.MOCK_MODE = True

        with (
            patch("app.routes.config_store.get_devices", return_value=devices),
            patch("app.routes.config_store.get_settings", return_value=settings),
            patch("app.routes.config_store.get_routines", return_value=config_store._default_for("routines")),
            patch("app.routes.config_store.save_devices"),
            patch("app.routes.config_store.save_settings"),
            patch("app.routes.gpio_controller.setup"),
        ):
            client = app.test_client()
            with client.session_transaction() as session:
                session["operator_authenticated"] = True

            response = client.post(
                "/api/setup",
                json={
                    "controller_name": "HauntOS Controller",
                    "mock_mode": False,
                    "outputs": {},
                    "inputs": {},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(audio_controller.MOCK_MODE)
        self.assertIsNone(video_controller.MOCK_MODE)

    def test_settings_validation_rejects_bad_types_and_bad_scheduler_times(self):
        invalid_type = {
            "mock_mode": "yes",
            "active_low_outputs": False,
            "active_low_inputs": True,
        }
        with self.assertRaises(ValueError):
            config_store.validate_config("settings", invalid_type)

        invalid_scheduler = {
            "mock_mode": True,
            "active_low_outputs": False,
            "active_low_inputs": True,
            "scheduler": {
                "enabled": True,
                "start_time": "99:99",
                "end_time": "22:00",
                "mode": "random",
                "interval_min": 120,
                "interval_max": 300,
                "routine": "IN1",
            },
        }
        with self.assertRaises(ValueError):
            config_store.validate_config("settings", invalid_scheduler)

    def test_scheduler_random_mode_ignores_empty_routines(self):
        self.assertIsNone(scheduler._choose_routine_id({"routine": "random"}, {"IN1": [], "IN2": []}))
        self.assertEqual(
            scheduler._choose_routine_id(
                {"routine": "random"},
                {"IN1": [], "IN2": [{"type": "wait", "duration": 1}]},
            ),
            "IN2",
        )


if __name__ == "__main__":
    unittest.main()
