@echo off
cd /d "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\astro_assistant"
"C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\.venv\Scripts\python.exe" -u -m streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
