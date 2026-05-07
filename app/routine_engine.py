"""Threaded routine engine for HauntOS.

Phase 6 executes tile sequences in background threads and provides a global
STOP path for outputs, audio, and video.
"""

from __future__ import annotations

import threading
import time
from typing import Any

try:
    from app import audio_controller, gpio_controller, video_controller
except ImportError:  # Allows running this file directly from the app folder.
    import audio_controller  # type: ignore
    import gpio_controller  # type: ignore
    import video_controller  # type: ignore


CHECK_INTERVAL = 0.05

_stop_event = threading.Event()
_threads: list[threading.Thread] = []
_lock = threading.Lock()
_status_lock = threading.Lock()
_run_counter = 0
_runtime_status: dict[str, Any] = {
    "routine_id": None,
    "tile_index": None,
    "tile": None,
    "run_id": None,
}
_active_runs: dict[int, dict[str, Any]] = {}


class RoutineConcurrencyError(RuntimeError):
    """Raised when a routine start is blocked by the active concurrency policy."""


def run_routine(
    tile_list: list[dict[str, Any]],
    routine_id: str | None = None,
    allow_concurrent: bool = False,
) -> threading.Thread:
    """Start a routine in a background thread and return the thread."""
    global _stop_event, _run_counter

    if not isinstance(tile_list, list):
        raise ValueError("Routine must be a list of tiles")
    if not isinstance(allow_concurrent, bool):
        raise ValueError("allow_concurrent must be true or false")

    with _lock:
        _prune_finished_threads()
        _enforce_concurrency_policy(allow_concurrent)
        if _stop_event.is_set():
            _stop_event = threading.Event()

        _run_counter += 1
        run_id = _run_counter
        routine_stop_event = _stop_event
        thread = threading.Thread(
            target=_run_tiles,
            args=(list(tile_list), routine_stop_event, routine_id, run_id),
            daemon=True,
        )
        _threads.append(thread)
        _active_runs[run_id] = {
            "run_id": run_id,
            "routine_id": routine_id,
            "allow_concurrent": allow_concurrent,
            "thread": thread,
            "started_at": time.time(),
            "tile_index": None,
            "tile": None,
        }
        thread.start()
        return thread


def stop_all() -> None:
    """Stop all running routines and immediately shut down outputs/media."""
    _stop_event.set()
    _clear_current_tile()
    audio_controller.stop_all_sounds()
    video_controller.stop_video()
    gpio_controller.all_off()


def get_runtime_status() -> dict[str, Any]:
    """Return the active routine and tile, if one is currently executing."""
    with _status_lock:
        return {
            "routine_id": _runtime_status.get("routine_id"),
            "tile_index": _runtime_status.get("tile_index"),
            "tile": dict(_runtime_status["tile"]) if isinstance(_runtime_status.get("tile"), dict) else None,
        }


def get_active_runs() -> list[dict[str, Any]]:
    """Return currently active routine runs for multi-run status UIs."""
    with _lock:
        _prune_finished_threads()
        runs = []
        for run_id, run in sorted(_active_runs.items()):
            tile = run.get("tile")
            runs.append(
                {
                    "run_id": run_id,
                    "routine_id": run.get("routine_id"),
                    "allow_concurrent": bool(run.get("allow_concurrent", False)),
                    "tile_index": run.get("tile_index"),
                    "tile": dict(tile) if isinstance(tile, dict) else None,
                    "started_at": run.get("started_at"),
                }
            )
        return runs


def is_running() -> bool:
    """Return True if any routine thread is still running."""
    with _lock:
        _prune_finished_threads()
        return any(thread.is_alive() for thread in _threads)


def _run_tiles(
    tile_list: list[dict[str, Any]],
    stop_event: threading.Event,
    routine_id: str | None,
    run_id: int,
) -> None:
    try:
        for index, tile in enumerate(tile_list):
            if stop_event.is_set():
                break
            _set_current_tile(run_id, routine_id, index, tile)
            _run_tile(tile, stop_event)
    finally:
        _finish_run(run_id)
        _clear_current_tile(run_id)
        if stop_event.is_set():
            gpio_controller.all_off()


def _run_tile(tile: dict[str, Any], stop_event: threading.Event) -> None:
    if not isinstance(tile, dict):
        print(f"Routine: skipping invalid tile: {tile}")
        return

    tile_type = tile.get("type")

    try:
        if tile_type == "output":
            _run_output_tile(tile, stop_event)
        elif tile_type == "wait":
            _interruptible_wait(_duration(tile), stop_event)
        elif tile_type == "sound":
            _run_sound_tile(tile)
        elif tile_type == "video":
            _run_video_tile(tile)
        elif tile_type == "all_off":
            _run_all_off_tile()
        else:
            print(f"Routine: unknown tile type: {tile_type}")
    except Exception as exc:
        print(f"Routine: tile failed ({tile_type}): {exc}")


def _run_output_tile(tile: dict[str, Any], stop_event: threading.Event) -> None:
    target = tile.get("target")
    action = str(tile.get("action", "")).lower()

    if not target:
        print("Routine: output tile missing target")
        return

    if action == "on":
        gpio_controller.turn_on(target)
    elif action == "off":
        gpio_controller.turn_off(target)
    elif action == "pulse":
        gpio_controller.turn_on(target)
        try:
            _interruptible_wait(_duration(tile), stop_event)
        finally:
            gpio_controller.turn_off(target)
    else:
        print(f"Routine: unknown output action: {action}")


def _run_sound_tile(tile: dict[str, Any]) -> None:
    filename = tile.get("file")
    if not filename:
        print("Routine: sound tile missing file")
        return

    mode = tile.get("mode", "play_and_continue")
    allow_concurrent = bool(tile.get("allow_concurrent", False))
    audio_controller.play_sound(filename, mode=mode, allow_concurrent=allow_concurrent)


def _run_video_tile(tile: dict[str, Any]) -> None:
    filename = tile.get("file")
    if not filename:
        print("Routine: video tile missing file")
        return

    mode = tile.get("mode", "play_and_continue")
    video_controller.play_video(filename, mode=mode)


def _run_all_off_tile() -> None:
    gpio_controller.all_off()
    audio_controller.stop_all_sounds()
    video_controller.stop_video()


def _interruptible_wait(duration: float, stop_event: threading.Event) -> None:
    if duration <= 0:
        return

    end_time = time.monotonic() + duration
    while not stop_event.is_set():
        remaining = end_time - time.monotonic()
        if remaining <= 0:
            return
        stop_event.wait(min(CHECK_INTERVAL, remaining))


def _duration(tile: dict[str, Any]) -> float:
    try:
        return max(0.0, float(tile.get("duration", 0)))
    except (TypeError, ValueError):
        return 0.0


def _prune_finished_threads() -> None:
    _threads[:] = [thread for thread in _threads if thread.is_alive()]
    finished_runs = [
        run_id
        for run_id, run in _active_runs.items()
        if not run.get("thread") or not run["thread"].is_alive()
    ]
    for run_id in finished_runs:
        _active_runs.pop(run_id, None)


def _enforce_concurrency_policy(new_allow_concurrent: bool) -> None:
    if not _active_runs:
        return

    if new_allow_concurrent and all(
        bool(run.get("allow_concurrent", False)) for run in _active_runs.values()
    ):
        return

    active_names = [
        str(run.get("routine_id") or f"run {run_id}")
        for run_id, run in sorted(_active_runs.items())
    ]
    active_text = ", ".join(active_names) if active_names else "another routine"
    raise RoutineConcurrencyError(
        f"{active_text} is already running. Stop the active routine or enable Allow Concurrent on both routines before starting another."
    )


def _set_current_tile(
    run_id: int,
    routine_id: str | None,
    tile_index: int,
    tile: dict[str, Any],
) -> None:
    with _status_lock:
        _runtime_status["run_id"] = run_id
        _runtime_status["routine_id"] = routine_id
        _runtime_status["tile_index"] = tile_index
        _runtime_status["tile"] = dict(tile)

    with _lock:
        run = _active_runs.get(run_id)
        if run is not None:
            run["tile_index"] = tile_index
            run["tile"] = dict(tile)


def _finish_run(run_id: int) -> None:
    with _lock:
        _active_runs.pop(run_id, None)


def _clear_current_tile(run_id: int | None = None) -> None:
    with _status_lock:
        if run_id is not None and _runtime_status.get("run_id") != run_id:
            return
        _runtime_status["run_id"] = None
        _runtime_status["routine_id"] = None
        _runtime_status["tile_index"] = None
        _runtime_status["tile"] = None


if __name__ == "__main__":
    test_routine = [
        {"type": "output", "target": "OUT1", "action": "pulse", "duration": 2},
        {"type": "wait", "duration": 1},
        {"type": "output", "target": "OUT2", "action": "pulse", "duration": 2},
    ]

    routine_thread = run_routine(test_routine)
    routine_thread.join()
    stop_all()
