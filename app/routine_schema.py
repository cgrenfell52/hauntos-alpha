"""Strict routine and tile validation for HauntOS configs and run requests."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


INPUT_IDS = ("IN1", "IN2", "IN3", "IN4")
OUTPUT_IDS = ("OUT1", "OUT2", "OUT3", "OUT4", "OUT5", "OUT6", "OUT7", "OUT8")
TILE_TYPES = {"output", "wait", "sound", "video", "all_off"}
OUTPUT_ACTIONS = {"on", "off", "pulse"}
MEDIA_MODES = {"play_and_continue", "wait_until_done"}
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4"}
MAX_DURATION_SECONDS = 3600.0

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._() -]*$")


def validate_routines(routines: Any, devices: dict[str, Any] | None = None) -> None:
    """Raise ValueError when a routines config is malformed."""
    normalize_routines(routines, devices)


def normalize_routines(routines: Any, devices: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Return routines with defaults applied after strict validation."""
    if not isinstance(routines, dict):
        raise ValueError("Routines config must be an object")

    input_ids = _input_ids(devices)
    unknown_ids = sorted(set(routines) - set(input_ids))
    if unknown_ids:
        raise ValueError(f"Unknown routine input id: {', '.join(unknown_ids)}")

    normalized: dict[str, list[dict[str, Any]]] = {}
    for input_id in input_ids:
        tiles = routines.get(input_id)
        if not isinstance(tiles, list):
            raise ValueError(f"Routine {input_id} must be a list of tiles")
        normalized[input_id] = normalize_tile_list(tiles, devices, context=f"Routine {input_id}")

    return normalized


def validate_tile_list(tile_list: Any, devices: dict[str, Any] | None = None, context: str = "Routine") -> None:
    """Raise ValueError when a tile list is malformed."""
    normalize_tile_list(tile_list, devices, context)


def normalize_tile_list(
    tile_list: Any,
    devices: dict[str, Any] | None = None,
    context: str = "Routine",
) -> list[dict[str, Any]]:
    """Return a normalized tile list after strict validation."""
    if not isinstance(tile_list, list):
        raise ValueError(f"{context} must be a list of tiles")

    return [
        normalize_tile(tile, devices, context=f"{context} tile {index + 1}")
        for index, tile in enumerate(tile_list)
    ]


def normalize_tile(
    tile: Any,
    devices: dict[str, Any] | None = None,
    context: str = "Tile",
) -> dict[str, Any]:
    """Return a normalized tile after strict validation."""
    if not isinstance(tile, dict):
        raise ValueError(f"{context} must be an object")

    tile_type = tile.get("type")
    if tile_type not in TILE_TYPES:
        raise ValueError(f"{context} has unsupported type: {tile_type}")

    if tile_type == "output":
        _reject_unknown_keys(tile, {"type", "target", "action", "duration"}, context)
        target = _required_string(tile, "target", context)
        if target not in _output_ids(devices):
            raise ValueError(f"{context} references unknown output target: {target}")

        action = _required_string(tile, "action", context).lower()
        if action not in OUTPUT_ACTIONS:
            raise ValueError(f"{context} output action must be one of: {', '.join(sorted(OUTPUT_ACTIONS))}")

        normalized = {"type": "output", "target": target, "action": action}
        if action == "pulse":
            normalized["duration"] = _duration(tile.get("duration"), "duration", context)
        elif "duration" in tile:
            normalized["duration"] = _duration(tile.get("duration"), "duration", context)
        return normalized

    if tile_type == "wait":
        _reject_unknown_keys(tile, {"type", "duration"}, context)
        return {"type": "wait", "duration": _duration(tile.get("duration"), "duration", context)}

    if tile_type == "sound":
        _reject_unknown_keys(tile, {"type", "file", "mode", "allow_concurrent"}, context)
        return {
            "type": "sound",
            "file": _media_filename(tile.get("file"), SUPPORTED_AUDIO_EXTENSIONS, context),
            "mode": _media_mode(tile.get("mode", "play_and_continue"), context),
            "allow_concurrent": _bool_flag(tile.get("allow_concurrent", False), "allow_concurrent", context),
        }

    if tile_type == "video":
        _reject_unknown_keys(tile, {"type", "file", "mode", "allow_concurrent"}, context)
        allow_concurrent = tile.get("allow_concurrent", False)
        if not isinstance(allow_concurrent, bool):
            raise ValueError(f"{context} allow_concurrent must be true or false")
        if allow_concurrent:
            raise ValueError(f"{context} video concurrency is not supported in this alpha")
        return {
            "type": "video",
            "file": _media_filename(tile.get("file"), SUPPORTED_VIDEO_EXTENSIONS, context),
            "mode": _media_mode(tile.get("mode", "play_and_continue"), context),
        }

    _reject_unknown_keys(tile, {"type"}, context)
    return {"type": "all_off"}


def _input_ids(devices: dict[str, Any] | None) -> tuple[str, ...]:
    inputs = devices.get("inputs", {}) if isinstance(devices, dict) else {}
    if isinstance(inputs, dict) and inputs:
        return tuple(inputs.keys())
    return INPUT_IDS


def _output_ids(devices: dict[str, Any] | None) -> tuple[str, ...]:
    outputs = devices.get("outputs", {}) if isinstance(devices, dict) else {}
    if isinstance(outputs, dict) and outputs:
        return tuple(outputs.keys())
    return OUTPUT_IDS


def _reject_unknown_keys(tile: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(tile) - allowed)
    if unknown:
        raise ValueError(f"{context} has unsupported field: {', '.join(unknown)}")


def _required_string(tile: dict[str, Any], key: str, context: str) -> str:
    value = tile.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} {key} is required")
    return value.strip()


def _duration(value: Any, label: str, context: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{context} {label} must be a number")
    try:
        duration = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} {label} must be a number") from exc

    if not math.isfinite(duration) or duration < 0:
        raise ValueError(f"{context} {label} must be greater than or equal to 0")
    if duration > MAX_DURATION_SECONDS:
        raise ValueError(f"{context} {label} must be {int(MAX_DURATION_SECONDS)} seconds or less")
    return duration


def _media_filename(value: Any, extensions: set[str], context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} media filename is required")

    filename = value.strip()
    if "/" in filename or "\\" in filename or ":" in filename:
        raise ValueError(f"{context} media filename must not contain path separators")
    if not _SAFE_FILENAME.match(filename):
        raise ValueError(f"{context} media filename contains unsupported characters")

    suffix = Path(filename).suffix.lower()
    if suffix not in extensions:
        allowed = ", ".join(sorted(extensions))
        raise ValueError(f"{context} media filename must end with one of: {allowed}")

    return filename


def _media_mode(value: Any, context: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} media mode must be a string")
    mode = value.lower()
    if mode not in MEDIA_MODES:
        raise ValueError(f"{context} media mode must be one of: {', '.join(sorted(MEDIA_MODES))}")
    return mode


def _bool_flag(value: Any, label: str, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context} {label} must be true or false")
    return value
