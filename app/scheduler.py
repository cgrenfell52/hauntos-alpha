"""Basic scheduler service for HauntOS.

Phase 15 keeps scheduling intentionally simple: one background thread, one
settings block, and one routine trigger at a time.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime
from typing import Any

try:
    from app import config_store, routine_engine
except ImportError:  # Allows running this file directly from the app folder.
    import config_store  # type: ignore
    import routine_engine  # type: ignore


LOGGER = logging.getLogger(__name__)

CHECK_INTERVAL = 1.0

_stop_event = threading.Event()
_scheduler_thread: threading.Thread | None = None
_lock = threading.Lock()
_next_run_at: float | None = None


def start_scheduler() -> None:
    """Start the scheduler background thread."""
    global _scheduler_thread

    with _lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return

        _stop_event.clear()
        _scheduler_thread = threading.Thread(
            target=scheduler_loop,
            name="HauntOSScheduler",
            daemon=True,
        )
        _scheduler_thread.start()
        LOGGER.info("Scheduler started")


def stop_scheduler(timeout: float = 1.0) -> None:
    """Stop the scheduler background thread."""
    global _scheduler_thread, _next_run_at

    _stop_event.set()
    thread = _scheduler_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)

    with _lock:
        if _scheduler_thread is thread:
            _scheduler_thread = None
        _next_run_at = None

    LOGGER.info("Scheduler stopped")


def scheduler_loop() -> None:
    """Poll scheduler settings once per second and run routines when due."""
    global _next_run_at

    while not _stop_event.is_set():
        try:
            settings = config_store.get_settings()
            scheduler_settings = get_scheduler_settings(settings)

            if not scheduler_settings.get("enabled", False) or not _in_active_hours(scheduler_settings):
                _next_run_at = None
            elif not _is_armed():
                _next_run_at = None
            else:
                now = time.monotonic()
                if _next_run_at is None:
                    _next_run_at = now + _next_interval(scheduler_settings)
                elif now >= _next_run_at:
                    _run_scheduled_routine(scheduler_settings)
                    _next_run_at = time.monotonic() + _next_interval(scheduler_settings)
        except Exception as exc:
            LOGGER.warning("Scheduler loop error: %s", exc)

        _stop_event.wait(CHECK_INTERVAL)


def get_scheduler_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return scheduler settings merged with defaults."""
    source = settings if settings is not None else config_store.get_settings()
    scheduler_settings = source.get("scheduler", {})
    if not isinstance(scheduler_settings, dict):
        scheduler_settings = {}

    merged = dict(config_store.DEFAULT_SCHEDULER)
    merged.update(scheduler_settings)
    return merged


def save_scheduler_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and save scheduler settings inside settings.json."""
    scheduler_settings = _normalize_scheduler_settings(data)
    settings = config_store.get_settings()
    settings["scheduler"] = scheduler_settings
    config_store.save_settings(settings)
    return scheduler_settings


def scheduler_status() -> dict[str, Any]:
    """Return scheduler settings plus runtime state."""
    settings = get_scheduler_settings()
    next_run_in = None
    if _next_run_at is not None:
        next_run_in = max(0, round(_next_run_at - time.monotonic()))

    return {
        "settings": settings,
        "running": _scheduler_thread is not None and _scheduler_thread.is_alive(),
        "armed": _is_armed(),
        "active_hours": _in_active_hours(settings),
        "next_run_in": next_run_in,
    }


def _normalize_scheduler_settings(data: dict[str, Any]) -> dict[str, Any]:
    enabled = data.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be true or false")

    mode_value = data.get("mode", config_store.DEFAULT_SCHEDULER["mode"])
    if not isinstance(mode_value, str):
        raise ValueError("Scheduler mode must be fixed or random")
    mode = mode_value.lower()
    if mode not in ("fixed", "random"):
        raise ValueError("Scheduler mode must be fixed or random")

    routine = data.get("routine", config_store.DEFAULT_SCHEDULER["routine"])
    if not isinstance(routine, str):
        raise ValueError("routine must be a string")
    routines = config_store.get_routines()
    if routine != "random" and routine not in routines:
        raise ValueError(f"Unknown routine: {routine}")

    interval_min = _positive_int(data.get("interval_min"), "interval_min")
    interval_max = _positive_int(data.get("interval_max"), "interval_max")
    if mode == "fixed":
        interval_max = interval_min
    elif interval_max < interval_min:
        raise ValueError("interval_max must be greater than or equal to interval_min")

    start_time = _normalize_time(data.get("start_time", config_store.DEFAULT_SCHEDULER["start_time"]))
    end_time = _normalize_time(data.get("end_time", config_store.DEFAULT_SCHEDULER["end_time"]))

    return {
        "enabled": enabled,
        "start_time": start_time,
        "end_time": end_time,
        "mode": mode,
        "interval_min": interval_min,
        "interval_max": interval_max,
        "routine": routine,
    }


def _run_scheduled_routine(settings: dict[str, Any]) -> None:
    routines = config_store.get_routines()
    routine_id = _choose_routine_id(settings, routines)
    if routine_id is None:
        LOGGER.warning("Scheduler found no routine to run")
        return

    tile_list = routines.get(routine_id, [])
    if not isinstance(tile_list, list):
        LOGGER.warning("Scheduler routine is invalid: %s", routine_id)
        return

    LOGGER.info("Scheduler running routine %s", routine_id)
    devices = config_store.get_devices()
    input_config = devices.get("inputs", {}).get(routine_id, {})
    allow_concurrent = (
        bool(input_config.get("allow_concurrent", False))
        if isinstance(input_config, dict)
        else False
    )
    try:
        routine_engine.run_routine(tile_list, routine_id=routine_id, allow_concurrent=allow_concurrent)
    except routine_engine.RoutineConcurrencyError as exc:
        LOGGER.info("Scheduler routine %s blocked: %s", routine_id, exc)


def _choose_routine_id(settings: dict[str, Any], routines: dict[str, Any]) -> str | None:
    if settings.get("routine") == "random":
        candidates = [
            routine_id
            for routine_id, tiles in routines.items()
            if isinstance(tiles, list) and len(tiles) > 0
        ]
        if not candidates:
            return None
        return random.choice(candidates)

    routine_id = str(settings.get("routine", "IN1"))
    return routine_id if routine_id in routines else None


def _next_interval(settings: dict[str, Any]) -> int:
    interval_min = int(settings.get("interval_min", 120))
    interval_max = int(settings.get("interval_max", interval_min))
    if settings.get("mode") == "random":
        return random.randint(interval_min, max(interval_min, interval_max))
    return interval_min


def _in_active_hours(settings: dict[str, Any]) -> bool:
    start_minutes = _time_to_minutes(str(settings.get("start_time", "19:00")))
    end_minutes = _time_to_minutes(str(settings.get("end_time", "22:00")))
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute

    if start_minutes == end_minutes:
        return True
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


def _is_armed() -> bool:
    """Return True when show mode is armed for automatic triggers."""
    return bool(config_store.get_settings().get("show_armed", False))


def _normalize_time(value: Any) -> str:
    text = str(value)
    minutes = _time_to_minutes(text)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _time_to_minutes(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("Time must use HH:MM format")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError("Time must use HH:MM format") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Time must use HH:MM format")
    return hour * 60 + minute


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if number <= 0:
        raise ValueError(f"{label} must be greater than 0")
    return number


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_scheduler()
    time.sleep(3)
    stop_scheduler()
