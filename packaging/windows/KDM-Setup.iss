; Kalupura Download Manager — Windows installer (Inno Setup 6+)
; Build after PyInstaller:  ISCC.exe /DMyAppVersion=X.Y.Z packaging\windows\KDM-Setup.iss
; Requires: dist\KDM\ populated (KDM.exe + browser-extension\ + …)

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "Kalupura Download Manager"
#define MyAppPublisher "Kalupura"
#define MyAppExeName "KDM.exe"
; Stable ID so upgrades replace the same ARP entry (Programs & Features)
; In .iss, use {{ and }} for literal braces (else {GUID} is parsed as a constant).
#define MyAppGuid "{{E8B4F2A1-3C9D-4E7F-8B1A-2D3E4F5A6B7C}}"

[Setup]
AppId={#MyAppGuid}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\..\dist\release
OutputBaseFilename=KDM-Setup-{#MyAppVersion}-x64
SetupIconFile=
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableProgramGroupPage=no
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "browserext"; Description: "Open browser to add KDM extension (Chrome / Edge)"; GroupDescription: "Browser integration:"; Flags: checkedonce

[Files]
Source: "..\..\dist\KDM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-browser-extension"; StatusMsg: "Preparing browser extension…"; Flags: postinstall skipifsilent; Tasks: browserext
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Kalupura Download Manager"; Flags: nowait postinstall skipifsilent
