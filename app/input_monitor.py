"""Input monitoring service for HauntOS.

Phase 10 polls configured inputs and starts the routine assigned to each input
when a trigger edge is detected.
"""

from __future__ import annotations

import threading
import time
from typing import Any

try:
    from app import config_store, gpio_controller, routine_engine
except ImportError:  # Allows running this file directly from the app folder.
    import config_store  # type: ignore
    import gpio_controller  # type: ignore
    import routine_engine  # type: ignore


POLL_INTERVAL = 0.03
CONFIG_REFRESH_INTERVAL = 1.0

_stop_event = threading.Event()
_monitor_thread: threading.Thread | None = None
_lock = threading.Lock()
_state_lock = threading.Lock()
_last_states: dict[str, bool] = {}
_last_trigger_times: dict[str, float] = {}
_cached_devices: dict[str, Any] | None = None
_last_config_load = 0.0


def start() -> None:
    """Start the background input polling thread."""
    global _monitor_thread

    with _lock:
        if _monitor_thread is not None and _monitor_thread.is_alive():
            return

        _stop_event.clear()
        _reset_state()
        _monitor_thread = threading.Thread(
            target=_monitor_loop,
            name="HauntOSInputMonitor",
            daemon=True,
        )
        _monitor_thread.start()
        print("Input monitor: started")


def stop(timeout: float = 1.0) -> None:
    """Stop the input polling thread."""
    global _monitor_thread

    _stop_event.set()
    thread = _monitor_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)

    with _lock:
        if _monitor_thread is thread:
            _monitor_thread = None

    print("Input monitor: stopped")


def is_running() -> bool:
    """Return True when the monitor thread is active."""
    return _monitor_thread is not None and _monitor_thread.is_alive()


def simulate_input(input_id: str) -> bool:
    """Trigger an input routine manually for mock-mode testing."""
    return _trigger_input(input_id, now=time.monotonic(), simulated=True)


def _monitor_loop() -> None:
    while not _stop_event.is_set():
        try:
            _poll_inputs()
        except Exception as exc:
            print(f"Input monitor: poll error: {exc}")
        _stop_event.wait(POLL_INTERVAL)


def _poll_inputs() -> None:
    devices = _get_devices_cached()
    inputs = devices.get("inputs", {})

    for input_id, input_config in inputs.items():
        if not _is_enabled(input_config):
            _last_states[input_id] = False
            continue

        active = _read_input_active(input_id)

        previously_active = _last_states.get(input_id, False)
        if active and not previously_active:
            _trigger_input(input_id, now=time.monotonic())

        _last_states[input_id] = active


def _trigger_input(input_id: str, now: float, simulated: bool = False) -> bool:
    devices = config_store.get_devices()
    inputs = devices.get("inputs", {})
    input_config = inputs.get(input_id)

    if not isinstance(input_config, dict):
        print(f"Input monitor: unknown input {input_id}")
        return False

    if not _is_enabled(input_config):
        print(f"Input monitor: ignoring disabled input {input_id}")
        return False

    if not _is_show_armed():
        print(f"Input monitor: ignoring {input_id}; show is stopped")
        return False

    with _state_lock:
        cooldown = _cooldown(input_config)
        last_trigger = _last_trigger_times.get(input_id, 0.0)
        if now - last_trigger < cooldown:
            print(f"Input monitor: cooldown active for {input_id}")
            return False
        _last_trigger_times[input_id] = now

    routines = config_store.get_routines()
    tile_list = routines.get(input_id, [])
    if not isinstance(tile_list, list):
        print(f"Input monitor: routine for {input_id} is not a tile list")
        return False

    source = "simulated input" if simulated else "input"
    print(f"Input monitor: {source} {input_id} triggered routine")
    try:
        routine_engine.run_routine(
            tile_list,
            routine_id=input_id,
            allow_concurrent=bool(input_config.get("allow_concurrent", False)),
        )
    except routine_engine.RoutineConcurrencyError as exc:
        print(f"Input monitor: {input_id} blocked: {exc}")
        return False
    return True


def _read_input_active(input_id: str) -> bool:
    if getattr(gpio_controller, "MOCK_MODE", True):
        return False

    try:
        return bool(gpio_controller.read_input(input_id))
    except Exception as exc:
        print(f"Input monitor: read failed for {input_id}: {exc}")
        return False


def _reset_state() -> None:
    global _cached_devices, _last_config_load

    with _state_lock:
        _cached_devices = config_store.get_devices()
        _last_config_load = time.monotonic()
        _last_states.clear()
        _last_trigger_times.clear()
        for input_id in _cached_devices.get("inputs", {}):
            _last_states[input_id] = False


def _get_devices_cached() -> dict[str, Any]:
    global _cached_devices, _last_config_load

    now = time.monotonic()
    if _cached_devices is None or now - _last_config_load >= CONFIG_REFRESH_INTERVAL:
        _cached_devices = config_store.get_devices()
        _last_config_load = now
    return _cached_devices


def _is_enabled(input_config: dict[str, Any]) -> bool:
    return bool(input_config.get("enabled", True))


def _cooldown(input_config: dict[str, Any]) -> float:
    try:
        return max(0.0, float(input_config.get("cooldown", 5)))
    except (TypeError, ValueError):
        return 5.0


def _is_show_armed() -> bool:
    return bool(config_store.get_settings().get("show_armed", False))


if __name__ == "__main__":
    gpio_controller.setup()
    start()
    simulate_input("IN1")
    time.sleep(0.2)
    stop()
    routine_engine.stop_all()
