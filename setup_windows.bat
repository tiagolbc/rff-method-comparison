@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_CMD=py"
) else (
  set "PYTHON_CMD=python"
)
%PYTHON_CMD% -m venv .venv
if errorlevel 1 goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto :error
pip install -r requirements.txt
if errorlevel 1 goto :error
echo.
echo Setup completed. Run run_rff_v25.bat to start the application.
pause
exit /b 0
:error
echo.
echo Setup failed. Confirm that Python 3.10 or newer is installed and available in PATH.
pause
exit /b 1
