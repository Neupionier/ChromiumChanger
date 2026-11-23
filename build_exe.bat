@echo off
rem Builds dist\ChromiumChanger\ChromiumChanger.exe (no Python needed to run it).
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.9+ is required to BUILD the exe. https://www.python.org/downloads/
    pause
    exit /b 1
  )
  set PY=python
) else (
  set PY=py -3
)
echo Installing build tools...
%PY% -m pip install --upgrade pip pyinstaller pillow
if errorlevel 1 goto :fail
echo Building...
%PY% -m PyInstaller --noconfirm --clean --windowed --uac-admin --name ChromiumChanger --icon assets\app.ico --add-data "assets;assets" app_entry.py
if errorlevel 1 goto :fail
if defined CC_SIGN_PFX goto :sign
if defined CC_SIGN_SUBJECT goto :sign
echo (not signed: set CC_SIGN_PFX / CC_SIGN_PASS or CC_SIGN_SUBJECT to sign, see README)
goto :zip
:sign
where signtool >nul 2>nul
if errorlevel 1 (
  echo signtool not found. Install the Windows SDK "Signing Tools" to sign. Skipping signing.
  goto :zip
)
echo Signing...
if defined CC_SIGN_PFX (
  signtool sign /f "%CC_SIGN_PFX%" /p "%CC_SIGN_PASS%" /fd sha256 /tr http://timestamp.digicert.com /td sha256 "dist\ChromiumChanger\ChromiumChanger.exe"
) else (
  signtool sign /n "%CC_SIGN_SUBJECT%" /fd sha256 /tr http://timestamp.digicert.com /td sha256 "dist\ChromiumChanger\ChromiumChanger.exe"
)
if errorlevel 1 goto :fail
:zip
echo Creating zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\ChromiumChanger\*' -DestinationPath 'dist\ChromiumChanger-win64.zip' -Force"
echo.
echo Done:
echo   dist\ChromiumChanger\ChromiumChanger.exe   (run directly)
echo   dist\ChromiumChanger-win64.zip              (portable package to share)
echo For a real installer, install Inno Setup 6 and run build_installer.bat
pause
exit /b 0
:fail
echo.
echo BUILD FAILED - see messages above.
pause
exit /b 1
