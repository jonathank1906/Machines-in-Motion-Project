@echo off
echo Starting Train Exhibit Control System...

start "FastAPI Backend" powershell -NoExit -Command ".\venv\Scripts\Activate.ps1; uvicorn backend.main:app --reload"
start "React Frontend" powershell -NoExit -Command "cd frontend; npm run dev"
start "Python Bridge" powershell -NoExit -Command "cd backend; py bridge.py"