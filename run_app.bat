@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" foxhole_train_run_app.py %*
) else (
  python foxhole_train_run_app.py %*
)
