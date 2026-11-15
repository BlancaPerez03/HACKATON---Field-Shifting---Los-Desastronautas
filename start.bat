@echo off
rem Field Shift: double-click to start. First time: creates .venv, installs packages, offers the
rem optional Earth Engine setup, then opens the page in the browser.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creating the Python environment .venv ...
  python -m venv .venv || goto :error
  .venv\Scripts\python.exe -m pip install -r requirements.txt || goto :error
)
.venv\Scripts\python.exe run.py %*
goto :eof
:error
echo.
echo Could not set up Python. Install Python 3.11 or later from https://www.python.org and try again.
pause
