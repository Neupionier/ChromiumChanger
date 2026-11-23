@echo off
rem Creates dist\ChromiumChanger-Setup.exe with Inno Setup 6 (run build_exe.bat first).
cd /d "%~dp0"
if not exist dist\ChromiumChanger\ChromiumChanger.exe (
  echo Run build_exe.bat first.
  pause
  exit /b 1
)
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe
if "%ISCC%"=="" (
  echo Inno Setup 6 not found. Install it from https://jrsoftware.org/isinfo.php and run again.
  pause
  exit /b 1
)
"%ISCC%" installer\ChromiumChanger.iss
if errorlevel 1 (
  echo INSTALLER BUILD FAILED
) else (
  echo Done: dist\ChromiumChanger-Setup.exe
)
pause
