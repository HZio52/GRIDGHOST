@echo off
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 (
 echo Python 3.12 is required. Install Python 3.12, then run this file again.
 pause
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if not exist ".venv\Scripts\python.exe" (
 echo Could not create the Python environment.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
 echo Dependency installation failed. Check your internet connection and the error above.
 pause
 exit /b 1
)
echo Open http://127.0.0.1:8000 after Application startup complete appears.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
