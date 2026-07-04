# HauntOS v0.1.0-alpha

HauntOS is a Raspberry Pi Halloween/show controller with a mobile operator dashboard, tile-based routines, physical inputs, output control, scheduler support, audio/video playback, and a local Flask web UI.

This alpha is aimed at field testing: fast setup, clear show state, guarded destructive actions, strict config validation, and a visible STOP EVERYTHING path.

## Current Alpha Highlights

- Quick Setup Wizard for controller, output, and input naming.
- Mobile operator dashboard for show state, controller status, scheduler readiness, active routines, trigger pads, and output state.
- Routine concurrency controls with exclusive-by-default inputs.
- Audio concurrency controls with exclusive-by-default sound tiles.
- Single-player video behavior for predictable show playback.
- Operator PIN protection for mutating control APIs after setup is complete.
- Purple/red logo and status badge for connected/offline state testing.
- Config import/export, factory reset, scheduler, media library, and system panels.

## Project Layout

```text
hauntos-alpha/
  app/
  audio/
  config/
  deploy/
  static/
  templates/
  tests/
  video/
  context.md
  README.md
  requirements.txt
```

Runtime config JSON and uploaded media are intentionally ignored by Git. The app recreates defaults and users can export/import backups from the UI.

## Development Setup

```powershell
cd C:\Users\cgren\OneDrive\Documents\hauntos-alpha
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

Open the web interface at:

```text
http://127.0.0.1:5000/
```

Local development does not require systemd. Service files under `deploy/` are only for Raspberry Pi deployment.

## Operator Login

After first-run setup is complete, mutating control APIs require an operator session. The default alpha operator PIN is:

```text
1031
```

Set a deployment PIN without editing files:

```bash
export HAUNTOS_OPERATOR_PIN="change-me"
export HAUNTOS_SECRET_KEY="use-a-long-random-secret"
```

For local-only bench testing, auth can be disabled with:

```bash
export HAUNTOS_AUTH_DISABLED=true
```

Do not disable auth on a show network.

## Verification

```powershell
node --check static/js/main.js
python -m compileall app
python -m unittest discover -s tests
```

GitHub Actions runs the same core checks on pushes and pull requests.

## Raspberry Pi Service Deployment

The systemd unit expects the project to live at `/home/pi/hauntos` and the virtual environment Python executable to exist at `/home/pi/hauntos/venv/bin/python`.

On the Pi:

```bash
cd /home/pi/hauntos
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
chmod +x deploy/install_service.sh deploy/uninstall_service.sh
./deploy/install_service.sh
```

Useful service commands:

```bash
sudo systemctl status hauntos.service
sudo systemctl restart hauntos.service
sudo systemctl stop hauntos.service
journalctl -u hauntos.service -f
```

## Raspberry Pi Hotspot Mode

Hotspot mode is optional. It lets the Pi create its own WiFi network named `HauntOS` so a phone or tablet can connect directly at a show site.

Defaults:

- SSID: `HauntOS`
- Password: `hauntcontroller`
- Pi address: `192.168.4.1`
- UI URL: `http://192.168.4.1:5000`

Enable hotspot mode on the Pi:

```bash
cd /home/pi/hauntos
chmod +x deploy/install_hotspot.sh
./deploy/install_hotspot.sh
```

Disable hotspot mode:

```bash
cd /home/pi/hauntos
./deploy/install_hotspot.sh --disable
./deploy/install_captive_portal.sh --disable
```

Full hotspot notes and rollback commands are in `deploy/hotspot_setup.md`.
