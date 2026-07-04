"""Flask entry point for HauntOS."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, jsonify

try:
    from app import app_log, gpio_controller, input_monitor, routine_engine, scheduler
    from app.routes import register_routes
except ImportError:  # Allows running this file directly from the app folder.
    import app_log  # type: ignore
    import gpio_controller  # type: ignore
    import input_monitor  # type: ignore
    import routine_engine  # type: ignore
    import scheduler  # type: ignore
    from routes import register_routes  # type: ignore


def create_app() -> Flask:
    """Create and configure the HauntOS Flask app."""
    app_log.setup_logging()
    base_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        static_folder=str(base_dir / "static"),
        template_folder=str(base_dir / "templates"),
    )
    app.secret_key = os.environ.get("HAUNTOS_SECRET_KEY") or secrets.token_hex(32)
    register_routes(app)

    try:
        gpio_controller.setup()
    except Exception as exc:
        print(f"Startup warning: GPIO setup failed: {exc}")

    try:
        input_monitor.start()
    except Exception as exc:
        print(f"Startup warning: input monitor failed: {exc}")

    try:
        scheduler.start_scheduler()
    except Exception as exc:
        print(f"Startup warning: scheduler failed: {exc}")

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"ok": False, "error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify({"ok": False, "error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception("Unhandled server error: %s", error)
        return jsonify({"ok": False, "error": "Internal server error"}), 500

    return app


def main() -> None:
    """Run the Flask API server."""
    app = create_app()
    try:
        app.run(host="0.0.0.0", port=5000, threaded=True)
    finally:
        shutdown_services()


def shutdown_services() -> None:
    """Stop background services and leave outputs in a safe state."""
    try:
        scheduler.stop_scheduler()
    except Exception as exc:
        print(f"Shutdown warning: scheduler stop failed: {exc}")

    try:
        input_monitor.stop()
    except Exception as exc:
        print(f"Shutdown warning: input monitor stop failed: {exc}")

    try:
        routine_engine.stop_all()
    except Exception as exc:
        print(f"Shutdown warning: routine stop failed: {exc}")

    try:
        gpio_controller.cleanup()
    except Exception as exc:
        print(f"Shutdown warning: GPIO cleanup failed: {exc}")


if __name__ == "__main__":
    main()
