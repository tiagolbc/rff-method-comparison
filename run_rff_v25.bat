@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" avhi_rff_method_comparison_gui_MATLAB_BRIDGE_v25_OPTIONAL_STI.py
) else (
  python avhi_rff_method_comparison_gui_MATLAB_BRIDGE_v25_OPTIONAL_STI.py
)
if errorlevel 1 pause
