"""Audio controller for HauntOS.

Phase 4 lists audio files, plays sounds with pygame when available, and falls
back to mock actions when mock mode is enabled or pygame cannot be loaded.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

try:
    from app import config_store
except ImportError:  # Allows running this file directly from the app folder.
    import config_store  # type: ignore


BASE_DIR = Path(__file__).resolve().parents[1]
AUDIO_DIR = BASE_DIR / "audio"
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav"}

PYGAME: Any = None
PYGAME_READY = False
MOCK_MODE: Optional[bool] = None
ACTIVE_CHANNELS: list[Any] = []


def list_audio_files() -> list[str]:
    """Return supported audio filenames from the audio directory."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    return sorted(
        path.name
        for path in AUDIO_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    )


def play_sound(filename: str, mode: str = "play_and_continue", allow_concurrent: bool = False) -> bool:
    """Play an audio file.

    Returns True when playback was started or mocked, and False when the file is
    missing or the mode is invalid.
    """
    if not isinstance(allow_concurrent, bool):
        print("Audio: allow_concurrent must be true or false")
        return False

    if mode not in {"play_and_continue", "wait_until_done"}:
        print(f"Audio: unsupported mode '{mode}'")
        return False

    audio_path = _safe_audio_path(filename)
    if audio_path is None:
        return False
    if not audio_path.exists():
        print(f"Audio: file not found: {filename}")
        return False

    if not allow_concurrent:
        stop_all_sounds()

    if _use_mock_audio():
        concurrency = "overlap allowed" if allow_concurrent else "exclusive"
        print(f"Audio: mock play {audio_path.name} ({mode}, {concurrency})")
        return True

    try:
        sound = PYGAME.mixer.Sound(str(audio_path))
        channel = sound.play()
    except Exception as exc:  # pygame can fail for device or codec reasons.
        print(f"Audio: could not play {audio_path.name}, using mock action ({exc})")
        print(f"Audio: mock play {audio_path.name} ({mode})")
        return True

    if channel is None:
        print(f"Audio: no available pygame channel for {audio_path.name}")
        return False

    ACTIVE_CHANNELS.append(channel)

    if mode == "wait_until_done":
        while channel.get_busy():
            time.sleep(0.05)
        _remove_inactive_channels()

    return True


def stop_all_sounds() -> None:
    """Stop all active sounds."""
    if _use_mock_audio():
        print("Audio: mock stop all sounds")
        return

    PYGAME.mixer.stop()
    ACTIVE_CHANNELS.clear()


def reset_runtime_config() -> None:
    """Refresh cached runtime settings after setup or config import changes."""
    global MOCK_MODE

    MOCK_MODE = None


def _use_mock_audio() -> bool:
    global MOCK_MODE

    if MOCK_MODE is None:
        settings = config_store.get_settings()
        MOCK_MODE = bool(settings.get("mock_mode", True))

    if MOCK_MODE:
        return True

    return not _ensure_pygame_ready()


def _ensure_pygame_ready() -> bool:
    global PYGAME, PYGAME_READY

    if PYGAME_READY:
        return True

    try:
        import pygame  # type: ignore

        PYGAME = pygame
        PYGAME.mixer.init()
        PYGAME_READY = True
        return True
    except Exception as exc:
        print(f"Audio: pygame unavailable, using mock mode ({exc})")
        PYGAME = None
        PYGAME_READY = False
        return False


def _safe_audio_path(filename: str) -> Path | None:
    path = (AUDIO_DIR / filename).resolve()
    audio_root = AUDIO_DIR.resolve()

    try:
        path.relative_to(audio_root)
    except ValueError:
        print(f"Audio: invalid filename outside audio directory: {filename}")
        return None

    if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        print(f"Audio: unsupported file type: {filename}")
        return None

    return path


def _remove_inactive_channels() -> None:
    ACTIVE_CHANNELS[:] = [
        channel for channel in ACTIVE_CHANNELS if channel is not None and channel.get_busy()
    ]


if __name__ == "__main__":
    print(list_audio_files())
    play_sound("test.mp3")
    stop_all_sounds()
