# HauntOS Codex Handoff Context

Last updated: 2026-07-04

## Project

HauntOS is a Raspberry Pi haunt/show controller built as a local Flask app. The UI is served from the Pi and controls routines made of output, wait, sound, video, and all-off tiles.

Workspace path:

```text
C:\Users\cgren\OneDrive\Documents\hauntos-alpha
```

Local dev URL:

```text
http://127.0.0.1:5000/
```

Run locally:

```powershell
python -m app.main
```

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

## Current Git State

This folder is its own Git repo. Runtime artifacts are ignored.

Ignored intentionally:

- `config/*.json`: live device/routine/settings data; app recreates defaults.
- `audio/*` and `video/*`: uploaded media; `.gitkeep` placeholders are tracked.
- `logs/`
- Python `__pycache__/` and `*.pyc`

Alpha tag:

```text
v0.1.0-alpha
```

## Implemented Features

- Quick Setup Wizard for controller, output, and input naming.
- Mobile operator dashboard for show state, controller status, scheduler readiness, active routines, trigger pads, and output state.
- Operator PIN login for mutating control APIs after setup completion.
- Config system with default JSON creation, strict validation, safe writes, import/export, and factory reset.
- GPIO controller with mock mode and Raspberry Pi GPIO support.
- Purple/red logo and centered CONNECTED/OFFLINE status badge.
- Audio controller with pygame fallback/mock mode and concurrent sound support.
- Video controller with mpv/vlc support, mock mode, and single-player replacement behavior.
- Threaded routine engine with hard stop support and exclusive/concurrent routine policy.
- Live routine status reporting from `/api/status`, including `active_runs`.
- Physical input monitor service with cooldown, enabled flag, active-low support, show-armed gate, and concurrency flag.
- Scheduler service with active hours, fixed/random intervals, chosen/random routine, and show-armed gate.
- Flask API for devices, routines, outputs, run/custom, stop, media, config backup/import/reset, scheduler, setup, system info, and auth.
- Web UI with fixed sidebar, dashboard, outputs, inputs/routine editor, audio, video, scheduler, setup, system, and login pages.
- Tile routine editor supports add/edit/delete/move/save/run.
- Active tile highlight while a routine is running.
- Start Show / Stop Show behavior:
  - Start Show arms physical inputs and scheduler.
  - Stop Show gracefully disarms future triggers and lets the current routine finish.
  - STOP EVERYTHING hard-cancels routines/media/outputs and disarms the show.
- Audio/video upload/list/delete UI with delete confirmation.
- Raspberry Pi deployment service files.
- Hotspot/captive portal deployment scripts and docs.
- GitHub Actions CI for Python compile, unit tests, and frontend syntax checks.

## Product Decisions

- Video stays single-player for the alpha; new video playback replaces the active video.
- Audio can overlap only when a sound tile opts into concurrency.
- Routines default to exclusive. A new routine can overlap only when every active run and the new run are concurrency-enabled.
- Hotspot controls should stay out of the alpha app UI. Hotspot is a deployment/network mode and can disconnect the user if toggled casually. Keep it as scripts/docs for now.
- Runtime config JSON is not committed. The app should create defaults and users can export/import backups through the UI.
- Uploaded media is not committed. Users upload files through the UI.

## Known Gaps / Next Good Work

- Confirm real GPIO behavior on a Raspberry Pi with `mock_mode: false`.
- Confirm real audio playback on Pi with pygame/audio device.
- Confirm real video playback on Pi with `mpv` or `vlc`.
- Hotspot scripts should be tested on a fresh Raspberry Pi OS install before relying on them in the field.
- Add a polished operator PIN change flow in the UI instead of relying on env/config values.
- Add integration tests around browser login and first-run setup redirect behavior.

## Important Files

- `app/main.py`: Flask app factory/startup/shutdown.
- `app/routes.py`: API, auth, and page routes.
- `app/config_store.py`: config defaults, load/save/validation.
- `app/gpio_controller.py`: outputs/inputs/mock GPIO.
- `app/routine_engine.py`: threaded routine execution and runtime status.
- `app/input_monitor.py`: physical input polling.
- `app/scheduler.py`: background scheduler.
- `app/audio_controller.py`: audio file list/play/stop.
- `app/video_controller.py`: video file list/play/stop.
- `static/js/main.js`: all frontend behavior.
- `static/css/style.css`: app styling.
- `templates/*.html`: Flask templates.
- `tests/`: unit and static regression tests.
- `deploy/`: Pi service and hotspot/captive portal deployment files.

## Verification Commands

```powershell
node --check static\js\main.js
python -m compileall app
python -m unittest discover -s tests
```

## Current User Preferences

- Dark professional Halloween/show-control look.
- Keep UI practical and control-panel-like, not a marketing page.
- Large readable buttons.
- STOP EVERYTHING must always be obvious and accessible.
- Avoid unnecessary technical text like GPIO numbers in everyday UI.
- Input/routine page should stay clean and tile-based.
- Save should be explicit; routine edits are local until Save.
- Toasts should use user-given input/output names where possible.
