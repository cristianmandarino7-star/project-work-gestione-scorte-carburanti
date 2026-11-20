@echo off
REM Avvia la dashboard nel browser (http://localhost:8501).
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python -m streamlit run app.py
) else (
    py -m streamlit run app.py
)
pause
