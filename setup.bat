@echo off
REM YouTube Downloader - Setup Script for Windows
REM This script sets up the project for local development

setlocal enabledelayedexpansion

echo.
echo =========================================
echo   YouTube Downloader Setup (Windows)
echo =========================================
echo.

REM Check Python version
echo Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found!
    echo Please install Python 3.9 or higher from https://www.python.org/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [OK] %PYTHON_VERSION% found

REM Create virtual environment
echo.
echo Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    echo [OK] Virtual environment created
) else (
    echo [INFO] Virtual environment already exists
)

REM Activate virtual environment
echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo Error: Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated

REM Install dependencies
echo.
echo Installing dependencies...
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)
echo [OK] Dependencies installed

REM Create directories
echo.
echo Creating directories...
if not exist "templates" mkdir templates
if not exist "downloads" mkdir downloads
if not exist "logs" mkdir logs
echo [OK] Directories created

REM Copy index.html to templates
echo.
echo Setting up templates...
if exist "index.html" (
    copy index.html templates\index.html >nul
    echo [OK] Template file copied
) else if exist "templates\index.html" (
    echo [OK] Template file already in place
) else (
    echo [WARNING] index.html not found in templates\
)

REM Check FFmpeg
echo.
echo Checking FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] FFmpeg not found!
    echo.
    echo Install FFmpeg:
    echo   1. Download from: https://ffmpeg.org/download.html
    echo   2. Add to PATH environment variable
    echo   3. Verify with: ffmpeg -version
) else (
    for /f "tokens=*" %%i in ('ffmpeg -version 2^>^&1 ^| findstr /r "ffmpeg version"') do (
        echo [OK] %%i
    )
)

REM Display summary
echo.
echo =========================================
echo Setup Complete!
echo =========================================
echo.
echo Next steps:
echo.
echo 1. Start the application:
echo    python app.py
echo.
echo 2. Open in browser:
echo    http://localhost:5000
echo.
echo 3. Test the API:
echo    curl http://localhost:5000/api/test
echo.
echo For production deployment, see DEPLOYMENT_GUIDE.md
echo.
pause
