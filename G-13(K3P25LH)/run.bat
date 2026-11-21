@echo off
cd /d "%~dp0"
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw main.py
) else (
    start "" python main.py
)
exit
