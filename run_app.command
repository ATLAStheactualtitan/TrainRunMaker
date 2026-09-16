#!/bin/bash
set -e
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# The venv lives outside iCloud Drive (~/Documents is synced) to stop iCloud from
# intermittently evicting/corrupting compiled Qt plugin binaries mid-sync.
VENV_DIR="$HOME/Library/Application Support/FoxholeTrainRunMaker/.venv"
PYTHON="$VENV_DIR/python/bin/python3"

if [ ! -x "$PYTHON" ]; then
  echo "Setting up project environment at $VENV_DIR (first run)..."
  mkdir -p "$VENV_DIR"
  BASE_PY="$(command -v python3.12 || true)"
  if [ -z "$BASE_PY" ] && [ -x "/opt/homebrew/bin/python3.12" ]; then
    BASE_PY="/opt/homebrew/bin/python3.12"
  fi
  if [ -z "$BASE_PY" ]; then
    BASE_PY="$(command -v python3)"
  fi
  "$BASE_PY" -m venv "$VENV_DIR/python"
  "$PYTHON" -m pip install --upgrade pip
  "$PYTHON" -m pip install --no-cache-dir -r "$PROJECT_ROOT/requirements.txt"
fi

# Self-heal: if Qt can't initialize (e.g. a corrupted plugin), reinstall PySide6 once and retry.
if ! "$PYTHON" -c "from PySide6.QtWidgets import QApplication; QApplication([])" >/dev/null 2>&1; then
  echo "Qt platform plugin failed to initialize; repairing PySide6..." >&2
  "$PYTHON" -m pip install --force-reinstall --no-cache-dir "$(grep -i '^PySide6' "$PROJECT_ROOT/requirements.txt")"
fi

exec "$PYTHON" "$PROJECT_ROOT/foxhole_train_run_app.py" "$@"
