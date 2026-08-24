@echo off
REM Sets up (if needed) and launches the hostel booking Django project on Windows,
REM then opens it in your default browser.
REM Usage: double-click this file, or run it from cmd: setup_and_run_windows.bat

setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
set "DEV_DIR=%PROJECT_ROOT%\dev"
set "VENV_DIR=%DEV_DIR%\venv"
set "PY=%VENV_DIR%\Scripts\python.exe"
set "URL=http://127.0.0.1:8000/"

if not exist "%PY%" (
    echo No virtual environment found, creating one at %VENV_DIR% ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 goto :error
)

echo Installing dependencies...
"%PY%" -m pip install --upgrade pip --quiet
if errorlevel 1 goto :error
"%PY%" -m pip install -r "%DEV_DIR%\requirements.txt" --quiet
if errorlevel 1 goto :error

cd /d "%DEV_DIR%"

echo Applying database migrations...
"%PY%" manage.py migrate
if errorlevel 1 goto :error

echo Setting up RBAC roles (Admin/Staff/Student groups)...
"%PY%" manage.py setup_roles
if errorlevel 1 goto :error

echo.
echo Starting development server in its own window at %URL% ...
REM cmd /k keeps that window open even if the server crashes, so any error is visible
REM instead of the window flashing shut.
start "Hostel Booking Server - close this window to stop it" cmd /k "%PY%" manage.py runserver

echo Waiting for the server to come up...
timeout /t 3 /nobreak >nul

echo Opening %URL% in your browser...
start "" "%URL%"

echo.
echo Done. The server keeps running in the "Hostel Booking Server" window.
echo If the page did not load, check that window for errors, then refresh your browser.
echo Close that window (or press Ctrl+C inside it) to stop the server.
echo.
pause
goto :eof

:error
echo.
echo Something went wrong ^(see above^). Aborting.
pause
exit /b 1

