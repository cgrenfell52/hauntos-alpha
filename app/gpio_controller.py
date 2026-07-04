"""GPIO controller for HauntOS.

Phase 3 supports mock mode for development machines and Raspberry Pi GPIO when
available. Outputs are always driven OFF during setup and cleanup.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

try:
    from app import config_store
except ImportError:  # Allows running this file directly from the app folder.
    import config_store  # type: ignore


GPIO: Any = None
MOCK_MODE = True
SETUP_COMPLETE = False
ACTIVE_LOW_OUTPUTS = False
ACTIVE_LOW_INPUTS = True

DEVICES: dict[str, Any] = {}
OUTPUT_STATES: dict[str, bool] = {}
MAX_MANUAL_PULSE_SECONDS = 30.0
_pulse_lock = threading.Lock()
_pulse_stop_event = threading.Event()
_active_pulses = 0


def setup() -> None:
    """Initialize GPIO and force every output OFF."""
    global GPIO, MOCK_MODE, SETUP_COMPLETE, ACTIVE_LOW_OUTPUTS, ACTIVE_LOW_INPUTS
    global DEVICES, OUTPUT_STATES

    settings = config_store.get_settings()
    DEVICES = config_store.get_devices()

    MOCK_MODE = bool(settings.get("mock_mode", True))
    ACTIVE_LOW_OUTPUTS = bool(settings.get("active_low_outputs", False))
    ACTIVE_LOW_INPUTS = bool(settings.get("active_low_inputs", True))

    if not MOCK_MODE:
        try:
            import RPi.GPIO as real_gpio  # type: ignore

            GPIO = real_gpio
        except ImportError:
            print("GPIO: RPi.GPIO unavailable, falling back to mock mode")
            GPIO = None
            MOCK_MODE = True

    if MOCK_MODE:
        print("GPIO: setup in mock mode")
    else:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        _setup_real_outputs()
        _setup_real_inputs()

    OUTPUT_STATES = {
        output_id: False for output_id, device in _outputs().items() if _is_enabled(device)
    }
    all_off()
    SETUP_COMPLETE = True


def cleanup() -> None:
    """Turn outputs OFF and release GPIO resources."""
    global SETUP_COMPLETE

    all_off()

    if MOCK_MODE:
        print("GPIO: cleanup in mock mode")
    elif GPIO is not None:
        GPIO.cleanup()

    SETUP_COMPLETE = False


def turn_on(output_id: str) -> None:
    """Turn an output ON and update tracked state."""
    _ensure_setup()
    device = _get_output(output_id)

    if MOCK_MODE:
        print(f"GPIO: mock turn ON {output_id} (GPIO{device['gpio']})")
    else:
        GPIO.output(device["gpio"], _gpio_on_value())

    OUTPUT_STATES[output_id] = True


def turn_off(output_id: str) -> None:
    """Turn an output OFF and update tracked state."""
    _ensure_setup()
    device = _get_output(output_id)

    if MOCK_MODE:
        print(f"GPIO: mock turn OFF {output_id} (GPIO{device['gpio']})")
    else:
        GPIO.output(device["gpio"], _gpio_off_value())

    OUTPUT_STATES[output_id] = False


def pulse(output_id: str, duration: float) -> None:
    """Turn an output ON for duration seconds, then OFF."""
    global _active_pulses

    if duration < 0:
        raise ValueError("Pulse duration must be greater than or equal to 0")
    if duration > MAX_MANUAL_PULSE_SECONDS:
        raise ValueError("Pulse duration must be 30 seconds or less")

    with _pulse_lock:
        if _active_pulses == 0:
            _pulse_stop_event.clear()
        _active_pulses += 1

    started = False
    try:
        turn_on(output_id)
        started = True
        _pulse_stop_event.wait(duration)
    finally:
        if started:
            turn_off(output_id)
        with _pulse_lock:
            _active_pulses = max(0, _active_pulses - 1)


def all_off() -> None:
    """Turn every enabled output OFF."""
    _pulse_stop_event.set()
    _load_devices_if_needed()

    for output_id, device in _outputs().items():
        if not _is_enabled(device):
            continue

        if MOCK_MODE:
            print(f"GPIO: mock turn OFF {output_id} (GPIO{device['gpio']})")
        elif GPIO is not None:
            GPIO.output(device["gpio"], _gpio_off_value())

        OUTPUT_STATES[output_id] = False


def get_output_states() -> dict[str, bool]:
    """Return a copy of the current output state dictionary."""
    _load_devices_if_needed()

    for output_id, device in _outputs().items():
        if _is_enabled(device) and output_id not in OUTPUT_STATES:
            OUTPUT_STATES[output_id] = False

    return dict(OUTPUT_STATES)


def read_input(input_id: str) -> bool:
    """Read an input and return True when it is active."""
    _ensure_setup()
    device = _get_input(input_id)

    if MOCK_MODE:
        print(f"GPIO: mock read {input_id} (GPIO{device['gpio']}) -> inactive")
        return False

    raw_value = GPIO.input(device["gpio"])
    return raw_value == _gpio_active_input_value()


def _setup_real_outputs() -> None:
    for device in _outputs().values():
        if _is_enabled(device):
            GPIO.setup(device["gpio"], GPIO.OUT, initial=_gpio_off_value())


def _setup_real_inputs() -> None:
    pull = GPIO.PUD_UP if ACTIVE_LOW_INPUTS else GPIO.PUD_DOWN
    for device in _inputs().values():
        if _is_enabled(device):
            GPIO.setup(device["gpio"], GPIO.IN, pull_up_down=pull)


def _ensure_setup() -> None:
    if not SETUP_COMPLETE:
        setup()


def _load_devices_if_needed() -> None:
    global DEVICES

    if not DEVICES:
        DEVICES = config_store.get_devices()


def _outputs() -> dict[str, Any]:
    _load_devices_if_needed()
    return DEVICES.get("outputs", {})


def _inputs() -> dict[str, Any]:
    _load_devices_if_needed()
    return DEVICES.get("inputs", {})


def _get_output(output_id: str) -> dict[str, Any]:
    output = _outputs().get(output_id)
    if output is None:
        raise KeyError(f"Unknown output: {output_id}")
    if not _is_enabled(output):
        raise ValueError(f"Output is disabled: {output_id}")
    return output


def _get_input(input_id: str) -> dict[str, Any]:
    input_device = _inputs().get(input_id)
    if input_device is None:
        raise KeyError(f"Unknown input: {input_id}")
    if not _is_enabled(input_device):
        raise ValueError(f"Input is disabled: {input_id}")
    return input_device


def _is_enabled(device: dict[str, Any]) -> bool:
    return bool(device.get("enabled", True))


def _gpio_on_value() -> int:
    return GPIO.LOW if ACTIVE_LOW_OUTPUTS else GPIO.HIGH


def _gpio_off_value() -> int:
    return GPIO.HIGH if ACTIVE_LOW_OUTPUTS else GPIO.LOW


def _gpio_active_input_value() -> int:
    return GPIO.LOW if ACTIVE_LOW_INPUTS else GPIO.HIGH


if __name__ == "__main__":
    setup()
    turn_on("OUT1")
    pulse("OUT2", 2)
    all_off()
    cleanup()
