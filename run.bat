@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw -m chromiumchanger %*
  goto :eof
)
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -3 -m chromiumchanger %*
  goto :eof
)
echo Python 3.9+ is required. Install it from https://www.python.org/downloads/
echo (check 'Add python.exe to PATH' during setup) and run again.
pause
