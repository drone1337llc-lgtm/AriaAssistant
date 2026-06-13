@echo off
REM Quick launcher for the AstroBud Streamlit dashboard.
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo [AstroBud] No .venv found. Using system Python.
)
streamlit run dashboard.py
