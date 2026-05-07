"""Flask API routes for HauntOS."""

from __future__ import annotations

import json
import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from flask import Flask, jsonify, redirect, render_template, request, send_file
from werkzeug.utils import secure_filename

try:
    from app import (
        app_log,
        audio_controller,
        config_store,
        gpio_controller,
        routine_schema,
        routine_engine,
        scheduler,
        system_tools,
        video_controller,
    )
except ImportError:  # Allows running this file directly from the app folder.
    import app_log  # type: ignore
    import audio_controller  # type: ignore
    import config_store  # type: ignore
    import gpio_controller  # type: ignore
    import routine_schema  # type: ignore
    import routine_engine  # type: ignore
    import scheduler  # type: ignore
    import system_tools  # type: ignore
    import video_controller  # type: ignore


LOGGER = logging.getLogger(__name__)


def register_routes(app: Flask) -> None:
    """Register API routes on the Flask app."""

    @app.get("/")
    def dashboard_page():
        if _needs_first_run_setup():
            return redirect("/setup")
        return render_template("dashboard.html", active_page="dashboard")

    @app.get("/outputs")
    def outputs_page():
        if _needs_first_run_setup():
            return redirect("/setup")
        return render_template("outputs.html", active_page="outputs")

    @app.get("/inputs")
    def inputs_page():
        if _needs_first_run_setup():
            return redirect("/setup")
        return render_template("inputs.html", active_page="inputs")

    @app.get("/audio")
    def audio_page():
        if _needs_first_run_setup():
            return redirect("/setup")
        return render_template("audio.html", active_page="audio")

    @app.get("/video")
    def video_page():
        if _needs_first_run_setup():
            return redirect("/setup")
        return render_template("video.html", active_page="video")

    @app.get("/system")
    def system_page():
        if _needs_first_run_setup():
            return redirect("/setup")
        return render_template("system.html", active_page="system")

    @app.get("/setup")
    def setup_page():
        return render_template("setup.html", active_page="setup")

    @app.get("/scheduler")
    def scheduler_page():
        if _needs_first_run_setup():
            return redirect("/setup")
        return render_template("scheduler.html", active_page="scheduler")

    @app.get("/api/status")
    def status():
        return _json_ok(
            {
                "version": system_tools.VERSION,
                "running": routine_engine.is_running(),
                "routine": routine_engine.get_runtime_status(),
                "active_runs": routine_engine.get_active_runs(),
                "outputs": gpio_controller.get_output_states(),
                "settings": config_store.get_settings(),
            }
        )

    @app.get("/api/devices")
    def get_devices():
        return _json_ok({"devices": config_store.get_devices()})

    @app.post("/api/devices")
    def save_devices():
        data = _json_body()
        if data is None:
            return _json_error("Request body must be a JSON object", 400)

        try:
            config_store.save_devices(data)
        except ValueError as exc:
            return _json_error(str(exc), 400)

        return _json_ok({"devices": config_store.get_devices()})

    @app.get("/api/routines")
    def get_routines():
        return _json_ok({"routines": config_store.get_routines()})

    @app.post("/api/routines")
    def save_routines():
        data = _json_body()
        if data is None:
            return _json_error("Request body must be a JSON object", 400)

        try:
            config_store.save_routines(data)
        except ValueError as exc:
            return _json_error(str(exc), 400)

        return _json_ok({"routines": config_store.get_routines()})

    @app.get("/api/scheduler")
    def get_scheduler():
        return _json_ok(scheduler.scheduler_status())

    @app.post("/api/scheduler")
    def save_scheduler():
        data = _json_body()
        if data is None:
            return _json_error("Request body must be a JSON object", 400)

        try:
            settings = scheduler.save_scheduler_settings(data)
        except ValueError as exc:
            return _json_error(str(exc), 400)

        return _json_ok({"settings": settings, "status": scheduler.scheduler_status()})

    @app.post("/api/run/input/<input_id>")
    def run_input(input_id: str):
        routines = config_store.get_routines()
        if input_id not in routines:
            return _json_error(f"Unknown input: {input_id}", 404)

        tile_list = routines[input_id]
        if not isinstance(tile_list, list):
            return _json_error(f"Routine for {input_id} must be a list", 400)

        try:
            devices = config_store.get_devices()
            normalized_tiles = routine_schema.normalize_tile_list(
                tile_list,
                devices,
                context=f"Routine {input_id}",
            )
            routine_engine.run_routine(
                normalized_tiles,
                routine_id=input_id,
                allow_concurrent=_input_allows_concurrency(devices, input_id),
            )
        except ValueError as exc:
            return _json_error(str(exc), 400)
        except routine_engine.RoutineConcurrencyError as exc:
            return _json_error(str(exc), 409)

        return _json_ok(
            {"running": routine_engine.is_running(), "input": input_id, "active_runs": routine_engine.get_active_runs()},
            202,
        )

    @app.post("/api/run/custom")
    def run_custom():
        data = request.get_json(silent=True)
        tile_list = data.get("tiles") if isinstance(data, dict) else data
        routine_id = data.get("routine_id") if isinstance(data, dict) else None
        allow_concurrent = data.get("allow_concurrent", False) if isinstance(data, dict) else False

        if not isinstance(tile_list, list):
            return _json_error("Request body must be a tile list or an object with a tiles list", 400)
        if not isinstance(allow_concurrent, bool):
            return _json_error("allow_concurrent must be true or false", 400)

        try:
            normalized_tiles = routine_schema.normalize_tile_list(
                tile_list,
                config_store.get_devices(),
                context="Custom routine",
            )
            routine_engine.run_routine(
                normalized_tiles,
                routine_id=routine_id,
                allow_concurrent=allow_concurrent,
            )
        except ValueError as exc:
            return _json_error(str(exc), 400)
        except routine_engine.RoutineConcurrencyError as exc:
            return _json_error(str(exc), 409)

        return _json_ok({"running": routine_engine.is_running(), "active_runs": routine_engine.get_active_runs()}, 202)

    @app.post("/api/stop")
    def stop():
        routine_engine.stop_all()
        _set_show_armed(False)
        return _json_ok({"running": routine_engine.is_running()})

    @app.post("/api/show/start")
    def start_show():
        settings = _set_show_armed(True)
        return _json_ok(
            {
                "running": routine_engine.is_running(),
                "settings": settings,
                "show_armed": True,
            }
        )

    @app.post("/api/show/stop")
    def stop_show():
        settings = _set_show_armed(False)
        return _json_ok(
            {
                "running": routine_engine.is_running(),
                "settings": settings,
                "show_armed": False,
                "graceful": True,
            }
        )

    @app.post("/api/output/<output_id>/on")
    def output_on(output_id: str):
        return _run_output_action(output_id, "on")

    @app.post("/api/output/<output_id>/off")
    def output_off(output_id: str):
        return _run_output_action(output_id, "off")

    @app.post("/api/output/<output_id>/pulse")
    def output_pulse(output_id: str):
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return _json_error("Request body must be a JSON object", 400)

        try:
            duration = float(data.get("duration", 1))
        except (TypeError, ValueError):
            return _json_error("duration must be a number", 400)

        if duration < 0:
            return _json_error("duration must be greater than or equal to 0", 400)

        return _run_output_action(output_id, "pulse", duration)

    @app.get("/api/audio")
    def audio_files():
        return _json_ok({"audio": audio_controller.list_audio_files()})

    @app.post("/api/audio/upload")
    def upload_audio():
        return _upload_media(
            directory=audio_controller.AUDIO_DIR,
            allowed_extensions=audio_controller.SUPPORTED_AUDIO_EXTENSIONS,
            response_key="audio",
            list_files=audio_controller.list_audio_files,
        )

    @app.delete("/api/audio/<filename>")
    def delete_audio(filename: str):
        return _delete_media(
            directory=audio_controller.AUDIO_DIR,
            allowed_extensions=audio_controller.SUPPORTED_AUDIO_EXTENSIONS,
            filename=filename,
            response_key="audio",
            list_files=audio_controller.list_audio_files,
        )

    @app.get("/api/video")
    def video_files():
        return _json_ok({"video": video_controller.list_video_files()})

    @app.post("/api/video/upload")
    def upload_video():
        return _upload_media(
            directory=video_controller.VIDEO_DIR,
            allowed_extensions=video_controller.SUPPORTED_VIDEO_EXTENSIONS,
            response_key="video",
            list_files=video_controller.list_video_files,
        )

    @app.delete("/api/video/<filename>")
    def delete_video(filename: str):
        return _delete_media(
            directory=video_controller.VIDEO_DIR,
            allowed_extensions=video_controller.SUPPORTED_VIDEO_EXTENSIONS,
            filename=filename,
            response_key="video",
            list_files=video_controller.list_video_files,
        )

    @app.get("/api/config/export")
    def export_configs():
        bundle = system_tools.export_config_bundle()
        payload = json.dumps(bundle, indent=2).encode("utf-8")
        return send_file(
            BytesIO(payload),
            mimetype="application/json",
            as_attachment=True,
            download_name="hauntos-config-backup.json",
        )

    @app.post("/api/config/import")
    def import_configs():
        uploaded_file = request.files.get("file")
        if uploaded_file is None or uploaded_file.filename == "":
            return _json_error("No backup file uploaded", 400)

        try:
            bundle = system_tools.parse_backup_json(uploaded_file)
            system_tools.import_config_bundle(bundle)
        except ValueError as exc:
            LOGGER.warning("Config import rejected: %s", exc)
            return _json_error(str(exc), 400)
        except OSError as exc:
            LOGGER.exception("Config import failed")
            return _json_error(f"Could not import backup: {exc}", 500)

        return _json_ok(
            {
                "devices": config_store.get_devices(),
                "routines": config_store.get_routines(),
                "settings": config_store.get_settings(),
            }
        )

    @app.post("/api/config/factory-reset")
    def reset_configs():
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict) or data.get("confirm") is not True:
            return _json_error("Factory reset requires confirmation", 400)

        LOGGER.warning("Factory reset requested")
        configs = system_tools.factory_reset()
        gpio_controller.setup()
        return _json_ok(configs)

    @app.get("/api/system/info")
    def system_info():
        settings = config_store.get_settings()
        return _json_ok(
            {
                "version": system_tools.VERSION,
                "controller_name": settings.get("controller_name", "HauntOS Controller"),
                "mock_mode": bool(settings.get("mock_mode", True)),
                "outputs": gpio_controller.get_output_states(),
                "running": routine_engine.is_running(),
                "ip_addresses": system_tools.get_ip_addresses(),
                "settings": settings,
                "deployment": system_tools.get_deployment_info(),
                "access": _access_info(),
            }
        )

    @app.post("/api/system/<action>")
    def system_action(action: str):
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict) or data.get("confirm") is not True:
            return _json_error("System action requires confirmation", 400)

        if action == "restart_service":
            routine_engine.stop_all()
        ok, message = system_tools.run_system_action(action)
        if not ok:
            LOGGER.warning("System action rejected: %s", message)
            return _json_error(message, 400)

        LOGGER.warning("System action requested: %s", action)
        return _json_ok({"message": message}, 202)

    @app.get("/api/logs")
    def logs():
        try:
            limit = min(200, max(1, int(request.args.get("limit", 80))))
        except ValueError:
            limit = 80
        errors_only = request.args.get("errors", "true").lower() != "false"
        return _json_ok({"logs": app_log.recent_lines(limit=limit, errors_only=errors_only)})

    @app.post("/api/setup")
    def save_setup():
        data = _json_body()
        if data is None:
            return _json_error("Request body must be a JSON object", 400)

        try:
            result = _apply_setup(data)
        except ValueError as exc:
            return _json_error(str(exc), 400)

        try:
            gpio_controller.setup()
        except Exception as exc:
            LOGGER.warning("GPIO setup refresh after setup save failed: %s", exc)

        return _json_ok(result)


def _run_output_action(output_id: str, action: str, duration: Optional[float] = None):
    try:
        if action == "on":
            gpio_controller.turn_on(output_id)
        elif action == "off":
            gpio_controller.turn_off(output_id)
        elif action == "pulse":
            gpio_controller.pulse(output_id, duration or 0)
        else:
            return _json_error(f"Unknown output action: {action}", 400)
    except KeyError as exc:
        return _json_error(str(exc), 404)
    except ValueError as exc:
        return _json_error(str(exc), 400)

    return _json_ok({"outputs": gpio_controller.get_output_states()})


def _upload_media(
    directory: Path,
    allowed_extensions: set[str],
    response_key: str,
    list_files,
):
    uploaded_file = request.files.get("file")
    if uploaded_file is None or uploaded_file.filename == "":
        return _json_error("No file uploaded", 400)

    safe_name = secure_filename(uploaded_file.filename)
    if not safe_name:
        return _json_error("Invalid filename", 400)

    suffix = Path(safe_name).suffix.lower()
    if suffix not in allowed_extensions:
        return _json_error(f"Unsupported file type: {suffix}", 400)

    directory.mkdir(parents=True, exist_ok=True)
    try:
        target_path = _unique_media_path(directory, safe_name)
        uploaded_file.save(target_path)
    except (OSError, ValueError) as exc:
        return _json_error(f"Could not save file: {exc}", 500)

    return _json_ok(
        {
            "filename": target_path.name,
            response_key: list_files(),
        },
        201,
    )


def _delete_media(
    directory: Path,
    allowed_extensions: set[str],
    filename: str,
    response_key: str,
    list_files,
):
    safe_name = secure_filename(filename)
    if safe_name != filename or not safe_name:
        return _json_error("Invalid filename", 400)

    suffix = Path(safe_name).suffix.lower()
    if suffix not in allowed_extensions:
        return _json_error(f"Unsupported file type: {suffix}", 400)

    path = _safe_media_path(directory, safe_name)
    if path is None:
        return _json_error("Invalid filename", 400)
    if not path.exists():
        return _json_error("File not found", 404)

    path.unlink()
    return _json_ok({"deleted": safe_name, response_key: list_files()})


def _safe_media_path(directory: Path, filename: str) -> Optional[Path]:
    media_root = directory.resolve()
    path = (media_root / filename).resolve()
    try:
        path.relative_to(media_root)
    except ValueError:
        return None
    return path


def _unique_media_path(directory: Path, filename: str) -> Path:
    path = _safe_media_path(directory, filename)
    if path is None:
        raise ValueError("Invalid filename")

    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    for index in range(1, 1000):
        candidate = _safe_media_path(directory, f"{stem}-{index}{suffix}")
        if candidate is not None and not candidate.exists():
            return candidate

    raise OSError("Could not create a unique filename")


def _apply_setup(data: dict[str, Any]) -> dict[str, Any]:
    controller_name = str(data.get("controller_name", "")).strip()
    if not controller_name:
        raise ValueError("Controller name is required")

    devices = config_store.get_devices()
    settings = config_store.get_settings()

    output_names = data.get("outputs", {})
    input_names = data.get("inputs", {})
    if not isinstance(output_names, dict) or not isinstance(input_names, dict):
        raise ValueError("Output and input names must be objects")

    for output_id, name in output_names.items():
        if output_id in devices.get("outputs", {}) and str(name).strip():
            devices["outputs"][output_id]["name"] = str(name).strip()

    for input_id, name in input_names.items():
        if input_id in devices.get("inputs", {}) and str(name).strip():
            devices["inputs"][input_id]["name"] = str(name).strip()

    settings["controller_name"] = controller_name
    if "mock_mode" in data:
        settings["mock_mode"] = bool(data["mock_mode"])
    settings["setup_complete"] = True

    config_store.save_devices(devices)
    config_store.save_settings(settings)

    return {"devices": devices, "routines": config_store.get_routines(), "settings": settings}


def _needs_first_run_setup() -> bool:
    return not bool(config_store.get_settings().get("setup_complete", False))


def _set_show_armed(armed: bool) -> dict[str, Any]:
    settings = config_store.get_settings()
    settings["show_armed"] = bool(armed)
    config_store.save_settings(settings)
    return settings


def _input_allows_concurrency(devices: dict[str, Any], input_id: str) -> bool:
    inputs = devices.get("inputs", {}) if isinstance(devices, dict) else {}
    input_config = inputs.get(input_id, {}) if isinstance(inputs, dict) else {}
    return bool(input_config.get("allow_concurrent", False)) if isinstance(input_config, dict) else False


def _access_info() -> dict[str, Any]:
    lan_urls = [f"http://{address}:5000" for address in system_tools.get_ip_addresses()]
    return {
        "current_url": request.host_url.rstrip("/"),
        "lan_urls": lan_urls,
        "hotspot_url": system_tools.HOTSPOT_URL,
    }


def _json_body() -> Optional[dict[str, Any]]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _json_ok(data: dict[str, Any], status: int = 200):
    payload = {"ok": True}
    payload.update(data)
    return jsonify(payload), status


def _json_error(message: str, status: int):
    return jsonify({"ok": False, "error": message}), status
