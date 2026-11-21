@echo off
cd /d "%~dp0"
echo Starting Quantum Traffic Router Pro...
python main.py
if errorlevel 1 (
    echo.
    echo ========================================================
    echo Error detected! If a library is missing, run:
    echo pip install numpy networkx matplotlib pillow
    echo ========================================================
    pause
)
