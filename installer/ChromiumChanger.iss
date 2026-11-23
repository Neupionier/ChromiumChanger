; Inno Setup script for ChromiumChanger (per-user install, no administrator needed)
#define AppName "ChromiumChanger"
#define AppVersion "0.2.0"

[Setup]
AppId={{6F1D2C5E-8B7A-4C3D-9E21-5A0B7C1D4E88}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=ChromiumChanger-Setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\ChromiumChanger.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\ChromiumChanger\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ChromiumChanger.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ChromiumChanger.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\ChromiumChanger.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

; User data lives in %LOCALAPPDATA%\ChromiumChanger and is intentionally NOT removed on uninstall.
