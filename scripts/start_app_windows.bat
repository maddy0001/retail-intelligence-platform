@echo off
rem Start Kartiq (FastAPI API + the built React app) on http://localhost:8100
rem Another port: set PORT=9000 before running this file.
cd /d "%~dp0.."
if "%PORT%"=="" set PORT=8100
set PY=python
if exist "venv\Scripts\python.exe" set PY=venv\Scripts\python.exe
echo Kartiq is starting on http://localhost:%PORT%   (press Ctrl+C to stop)
"%PY%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port %PORT%
