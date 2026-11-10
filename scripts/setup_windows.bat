@echo off
rem One-time setup for Kartiq on Windows:
rem   a Python virtual environment, the packages, then scripts\setup_kartiq.py
rem   (MongoDB check, real data, synthetic activity, models, demo accounts).
cd /d "%~dp0.."
rem Prefer a Python that every package has ready-made builds for (3.15 is too new for one of them).
if not exist "venv\Scripts\python.exe" (
  echo Creating a Python virtual environment in venv ...
  for %%V in (3.13 3.12 3.14 3.11) do (
    if not exist "venv\Scripts\python.exe" py -%%V -m venv venv 2>nul
  )
  if not exist "venv\Scripts\python.exe" python -m venv venv
)
"venv\Scripts\python.exe" --version 2>nul
if not exist "venv\Scripts\python.exe" (
  echo Could not create the virtual environment.
  echo Install Python 3.11, 3.12 or 3.13 from https://www.python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
echo Installing the Python packages (first time: a few minutes) ...
"venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
"venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo Installing the packages failed. See the message above.
  pause
  exit /b 1
)
"venv\Scripts\python.exe" scripts\setup_kartiq.py %*
pause
