"""Local system helpers for HauntOS product polish features."""

from __future__ import annotations

import json
import platform
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from app import config_store, routine_schema
except ImportError:  # Allows running this file directly from the app folder.
    import config_store  # type: ignore
    import routine_schema  # type: ignore


VERSION = "v0.1.0-alpha"
SERVICE_NAME = "hauntos.service"
BACKUP_VERSION = 1
HOTSPOT_URL = "http://192.168.4.1:5000"


def export_config_bundle() -> dict[str, Any]:
    """Return a JSON-serializable backup bundle for all config files."""
    return {
        "backup_version": BACKUP_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "configs": {
            "devices": config_store.get_devices(),
            "routines": config_store.get_routines(),
            "settings": config_store.get_settings(),
        },
    }


def import_config_bundle(bundle: dict[str, Any]) -> None:
    """Validate and replace all known configs from a backup bundle."""
    configs = _extract_configs(bundle)
    config_store.validate_config("devices", configs["devices"])
    routine_schema.validate_routines(configs["routines"], configs["devices"])
    config_store.validate_config("settings", configs["settings"])

    config_store.save_devices(configs["devices"])
    config_store.save_routines(configs["routines"])
    config_store.save_settings(configs["settings"])


def factory_reset() -> dict[str, Any]:
    """Restore default V1 config files and return the resulting configs."""
    config_store.reset_all_configs()
    return {
        "devices": config_store.get_devices(),
        "routines": config_store.get_routines(),
        "settings": config_store.get_settings(),
    }


def get_ip_addresses() -> list[str]:
    """Return likely local IPv4 addresses."""
    addresses: set[str] = set()

    try:
        hostname = socket.gethostname()
        for result in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = result[4][0]
            if address and not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            address = sock.getsockname()[0]
            if address and not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass

    return sorted(addresses)


def get_deployment_info() -> dict[str, Any]:
    """Return local deployment signals for the System page."""
    system_name = platform.system()
    pi_model = _raspberry_pi_model()
    service_state = _service_state() if system_name == "Linux" else "Unavailable"

    return {
        "platform": system_name,
        "is_raspberry_pi": bool(pi_model),
        "pi_model": pi_model or "Not detected",
        "service": service_state,
        "hotspot_url": HOTSPOT_URL,
    }


def run_system_action(action: str) -> tuple[bool, str]:
    """Run a guarded local system action when supported."""
    command = _command_for_action(action)
    if command is None:
        return False, f"Unsupported system action: {action}"

    if platform.system() != "Linux":
        return False, f"{action} is only available on Linux/Raspberry Pi deployments"

    executable = command[0]
    if "/" not in executable and _which(executable) is None:
        return False, f"Required command not found: {executable}"

    try:
        subprocess.Popen(command)
    except OSError as exc:
        return False, f"Could not start {action}: {exc}"

    return True, f"{action} requested"


def parse_backup_json(file_storage) -> dict[str, Any]:
    """Read an uploaded backup file as JSON."""
    raw = file_storage.read()
    if not raw:
        raise ValueError("Backup file is empty")

    try:
        text = raw.decode("utf-8-sig")
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Backup file must be valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Backup file must contain a JSON object")

    return data


def _extract_configs(bundle: dict[str, Any]) -> dict[str, Any]:
    configs = bundle.get("configs")
    if not isinstance(configs, dict):
        raise ValueError("Backup must contain a configs object")

    required = ("devices", "routines", "settings")
    missing = [name for name in required if name not in configs]
    if missing:
        raise ValueError(f"Backup is missing config: {', '.join(missing)}")

    return {name: configs[name] for name in required}


def _command_for_action(action: str) -> list[str] | None:
    if action == "reboot":
        return ["systemctl", "reboot"]
    if action == "shutdown":
        return ["systemctl", "poweroff"]
    if action == "restart_service":
        return ["systemctl", "restart", SERVICE_NAME]
    return None


def _raspberry_pi_model() -> str | None:
    model_path = Path("/proc/device-tree/model")
    try:
        model = model_path.read_text(encoding="utf-8", errors="ignore").strip("\x00\n ")
    except OSError:
        return None

    return model if "Raspberry Pi" in model else None


def _service_state() -> str:
    if platform.system() != "Linux" or _which("systemctl") is None:
        return "Unavailable"

    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Unknown"

    state = result.stdout.strip()
    return state.title() if state else "Unknown"


def _which(command: str) -> str | None:
    for directory in "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin".split(":"):
        candidate = Path(directory) / command
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None
