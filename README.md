# Foxhole Train Run Maker

Desktop app and renderer for live base allegiance overlays using **WarAPI Live-1** only.

## What It Does

- Pings WarAPI Live-1 on startup.
- Automatically loads and renders on app startup.
- Pulls live map data and confirms base allegiance (`teamId`).
- Renders only structure IDs: `45`, `56`, `57`, `58`.
- Uses nearest map text marker for each base name label.
- Displays map directly in the app (no overlay image/log is saved by the app).
- Click behavior:
  - Hollow green/blue circles for allegiance
  - Click to fill selected circles
  - Click multiple circles to draw path lines in selection order
  - Click a selected circle again to unselect and remove related path segments

## Requirements

- Python 3.10+
- Internet access
- Internet access to WarAPI Live-1

Install dependency:

```bash
python -m pip install -r requirements.txt
```

## Run (macOS)

Recommended:

```bash
./run_app.command
```

On first run this creates a virtual environment at `~/Library/Application Support/FoxholeTrainRunMaker/.venv` and installs dependencies automatically. This location is intentionally outside `~/Documents`/`~/Desktop` because iCloud Drive syncing those folders can intermittently corrupt compiled Qt plugin binaries, causing "Could not find the Qt platform plugin cocoa" errors. The launcher also self-heals: it verifies Qt can initialize before each run and automatically repairs the PySide6 install if not.

Do not start the app with the system `python3`, and do not move the virtual environment into an iCloud-synced folder.

## Downloadable Releases

GitHub Actions builds downloadable desktop packages for Windows x64, macOS Intel, and macOS Apple Silicon. To publish a release, push a version tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The `Build Desktop Releases` workflow creates a GitHub Release with one zip file per platform. Each zip contains the complete application folder; launch `FoxholeTrainRunMaker.exe` on Windows or open `FoxholeTrainRunMaker.app` on macOS. The packaged builds include the map atlas and cargo item list, so Python is not required on the user's machine.

## Run (Windows)

Option 1:

```bat
python foxhole_train_run_app.py
```

Option 2:

```bat
run_app.bat
```

## Notes

- API endpoint is fixed to Live-1:
  - `https://war-service-live.foxholeservices.com/api`
- If the API ping fails, generation stops and shows the error.
