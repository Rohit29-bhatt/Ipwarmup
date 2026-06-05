@echo off
title IP Warmup Tool — Setup ^& Launch
color 0A

echo.
echo  ==========================================================
echo   IP Warmup Automation Tool — Windows Setup
echo  ==========================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Please install Python 3.10+ from https://python.org
    pause & exit /b 1
)
echo  [OK] Python found.

:: Create virtual environment
if not exist "venv" (
    echo  [..] Creating virtual environment...
    python -m venv venv
)
echo  [OK] Virtual environment ready.

:: Activate and install
echo  [..] Installing dependencies (this may take ~2 minutes first time)...
call venv\Scripts\activate.bat
pip install -q -r requirements.txt

:: Install Playwright browsers
echo  [..] Installing Playwright browsers (Chromium)...
python -m playwright install chromium

echo.
echo  ==========================================================
echo   Setup complete! Starting server...
echo   Open your browser at:  http://localhost:5000
echo  ==========================================================
echo.

python app.py
pause
