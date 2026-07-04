"""Video controller for HauntOS.

Phase 5 lists video files, starts fullscreen playback through mpv or VLC, and
falls back to mock actions when mock mode is enabled.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

try:
    from app import config_store
except ImportError:  # Allows running this file directly from the app folder.
    import config_store  # type: ignore


BASE_DIR = Path(__file__).resolve().parents[1]
VIDEO_DIR = BASE_DIR / "video"
SUPPORTED_VIDEO_EXTENSIONS = {".mp4"}

CURRENT_PROCESS: Optional[subprocess.Popen] = None
MOCK_MODE: Optional[bool] = None


def list_video_files() -> list[str]:
    """Return supported video filenames from the video directory."""
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    return sorted(
        path.name
        for path in VIDEO_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    )


def play_video(filename: str, mode: str = "play_and_continue") -> bool:
    """Start fullscreen video playback without blocking the main thread."""
    if mode not in {"play_and_continue", "wait_until_done"}:
        print(f"Video: unsupported mode '{mode}'")
        return False

    video_path = _safe_video_path(filename)
    if video_path is None:
        return False
    if not video_path.exists():
        print(f"Video: file not found: {filename}")
        return False

    stop_video()

    if _use_mock_video():
        print(f"Video: mock play {video_path.name} ({mode})")
        return True

    command = _player_command(video_path)
    if command is None:
        print("Video: no supported video player found, using mock action")
        print(f"Video: mock play {video_path.name} ({mode})")
        return True

    started = _start_process(command, video_path.name)
    if started and mode == "wait_until_done":
        _wait_for_current_process()
    return started


def stop_video() -> None:
    """Stop the currently running video process, if any."""
    global CURRENT_PROCESS

    if CURRENT_PROCESS is None:
        if _use_mock_video():
            print("Video: mock stop video")
        return

    if CURRENT_PROCESS.poll() is None:
        CURRENT_PROCESS.terminate()
        try:
            CURRENT_PROCESS.wait(timeout=3)
        except subprocess.TimeoutExpired:
            CURRENT_PROCESS.kill()
            CURRENT_PROCESS.wait(timeout=3)

    CURRENT_PROCESS = None


def reset_runtime_config() -> None:
    """Refresh cached runtime settings after setup or config import changes."""
    global MOCK_MODE

    MOCK_MODE = None


def _use_mock_video() -> bool:
    global MOCK_MODE

    if MOCK_MODE is None:
        settings = config_store.get_settings()
        MOCK_MODE = bool(settings.get("mock_mode", True))

    return MOCK_MODE


def _player_command(video_path: Path) -> Optional[list[str]]:
    mpv_path = shutil.which("mpv")
    if mpv_path:
        return [mpv_path, "--fullscreen", "--really-quiet", str(video_path)]

    vlc_path = shutil.which("vlc") or shutil.which("cvlc")
    if vlc_path:
        return [vlc_path, "--fullscreen", "--play-and-exit", str(video_path)]

    return None


def _start_process(command: list[str], filename: str) -> bool:
    global CURRENT_PROCESS

    try:
        CURRENT_PROCESS = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError as exc:
        CURRENT_PROCESS = None
        print(f"Video: could not start player for {filename}, using mock action ({exc})")
        print(f"Video: mock play {filename}")
        return True


def _wait_for_current_process() -> None:
    global CURRENT_PROCESS

    process = CURRENT_PROCESS
    if process is None:
        return

    while process.poll() is None:
        time.sleep(0.05)

    if CURRENT_PROCESS is process:
        CURRENT_PROCESS = None


def _safe_video_path(filename: str) -> Optional[Path]:
    path = (VIDEO_DIR / filename).resolve()
    video_root = VIDEO_DIR.resolve()

    try:
        path.relative_to(video_root)
    except ValueError:
        print(f"Video: invalid filename outside video directory: {filename}")
        return None

    if path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        print(f"Video: unsupported file type: {filename}")
        return None

    return path


if __name__ == "__main__":
    print(list_video_files())
    play_video("test.mp4")
    stop_video()
