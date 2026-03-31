@echo off
echo MuleSoft Get Logs Agent - py Version
echo ========================================
echo.

REM Ensure we run from this script's directory so relative paths work
cd /d "%~dp0"

REM Check if py is available
py --version >nul 2>&1
if errorlevel 1 (
    echo Error: py is not installed or not in PATH
    echo Please install py 3.8 or higher
    pause
    exit /b 1
)

echo py found. Starting application...
echo.

REM Install dependencies if needed
echo Installing dependencies...
py -m pip install -r requirements.txt
if errorlevel 1 (
    echo Error installing dependencies
    pause
    exit /b 1
)

echo.
echo Starting Flask application...
echo Dashboard will be available at: http://localhost:3000
echo Press Ctrl+C to stop the server
echo.

REM Start the application
py app.py

pause
