@echo off
rem Same as run.bat but keeps a console window open so errors are visible.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python -m chromiumchanger %*
) else (
  py -3 -m chromiumchanger %*
)
pause
