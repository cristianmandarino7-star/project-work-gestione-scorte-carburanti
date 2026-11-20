@echo off
REM Installazione pulita: crea un ambiente virtuale .venv e installa le librerie.
cd /d "%~dp0"
py -m venv .venv || (echo Python non trovato: installarlo da python.org o con "winget install Python.Python.3.12" & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
echo.
echo Installazione completata. Avviare la dashboard con avvia_dashboard.bat
pause
