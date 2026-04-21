; Kalupura Download Manager — Windows installer (Inno Setup 6+)
; Build: ISCC.exe /DMyAppVersion=X.Y.Z packaging\windows\KDM-Setup.iss
; AppId must be a plain string — no {GUID} syntax (ISCC treats { as constants).

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "Kalupura Download Manager"

[Setup]
AppId=KalupuraKDMReleaseId2026
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Kalupura
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\..\dist\release
OutputBaseFilename=KDM-Setup-{#MyAppVersion}-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableProgramGroupPage=no
UninstallDisplayIcon={app}\KDM.exe
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "browserext"; Description: "Open browser to add KDM extension (Chrome / Edge)"; GroupDescription: "Browser integration:"; Flags: checkedonce

[Files]
Source: "..\..\dist\KDM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\KDM.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\KDM.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KDM.exe"; Parameters: "--install-browser-extension"; StatusMsg: "Preparing browser extension…"; Flags: postinstall skipifsilent; Tasks: browserext
Filename: "{app}\KDM.exe"; Description: "Launch Kalupura Download Manager"; Flags: nowait postinstall skipifsilent
