@echo off
REM Launch the Aria Brain Streamlit dashboard.
REM dashboard.py lives in brain/ (one level up from aria/).
cd /d "%~dp0..\brain"

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo [Aria] No brain\.venv found. Using system Python.
)

REM Install streamlit if missing (first-time setup).
python -c "import streamlit" 2>nul || pip install streamlit --quiet

streamlit run dashboard.py --server.port 8501 --server.headless true
