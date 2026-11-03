@echo off
echo Starting Train Exhibit Control System...

:: Terminal 1: FastAPI Backend
start "FastAPI Backend" powershell -NoExit -Command ".\venv\Scripts\Activate.ps1; uvicorn backend.main:app --reload"

:: Terminal 2: React Frontend
start "React Frontend" powershell -NoExit -Command "cd frontend; npm run dev"

:: Terminal 3: Python Bridge
start "Python Bridge" powershell -NoExit -Command "cd tests; py bridge.py"