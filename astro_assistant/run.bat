@echo off
REM Quick launcher for AstroBud main loop. Activates the venv if present.
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo [AstroBud] No .venv found. Using system Python. (Recommended: python -m venv .venv)
)
python main_astro.py
