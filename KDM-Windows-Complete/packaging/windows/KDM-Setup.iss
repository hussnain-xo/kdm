; Kalupura Download Manager — Windows installer (Inno Setup 6+)
; https://jrsoftware.org/isinfo.php  — Inno Setup 6+
; Build: ISCC.exe /DMyAppVersion=X.Y.Z packaging\windows\KDM-Setup.iss

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
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; --- Browser (Chromium allows --load-extension for this session; permanent still needs Load unpacked once) ---
Name: "chromeload"; Description: "Start Chrome with KDM extension (instant use in this Chrome window)"; GroupDescription: "Browser integration:"; Flags: checkedonce
Name: "edgeload"; Description: "Start Edge with KDM extension (instant use in this Edge window)"; GroupDescription: "Browser integration:"; Flags: unchecked
Name: "extwizard"; Description: "Show setup steps (open extension folder + extensions page for «Load unpacked»)"; GroupDescription: "Browser integration:"; Flags: checkedonce

[Files]
Source: "..\..\dist\KDM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\KDM.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\KDM.exe"; Tasks: desktopicon

[Run]
; 1) Optional: Chrome --load-extension (session load; closest to «one click» without Chrome Web Store)
Filename: "{code:GetChromeExe}"; Parameters: "--load-extension=""{app}\browser-extension"""; Flags: nowait postinstall skipifsilent shellexec; Tasks: chromeload; Check: ChromeExeOk

; 2) Optional: Edge --load-extension
Filename: "{code:GetEdgeExe}"; Parameters: "--load-extension=""{app}\browser-extension"""; Flags: nowait postinstall skipifsilent shellexec; Tasks: edgeload; Check: EdgeExeOk

; 3) Optional: small wizard (folder in Explorer + extension pages + message)
Filename: "{app}\KDM.exe"; Parameters: "--install-browser-extension"; StatusMsg: "Opening KDM browser extension helper…"; Flags: postinstall skipifsilent waituntilterminated; Tasks: extwizard

; 4) Launch main app (stays open)
Filename: "{app}\KDM.exe"; Description: "Launch Kalupura Download Manager"; Flags: nowait postinstall skipifsilent

[Code]
function GetChromeExe(Param: string): string;
var
  P: string;
begin
  P := ExpandConstant('{pf64}\Google\Chrome\Application\chrome.exe');
  if FileExists(P) then begin Result := P; Exit; end;
  P := ExpandConstant('{pf}\Google\Chrome\Application\chrome.exe');
  if FileExists(P) then begin Result := P; Exit; end;
  P := ExpandConstant('{localappdata}\Google\Chrome\Application\chrome.exe');
  if FileExists(P) then begin Result := P; Exit; end;
  Result := '';
end;

function ChromeExeOk: Boolean;
begin
  Result := (GetChromeExe('') <> '') and IsTaskSelected('chromeload');
end;

function GetEdgeExe(Param: string): string;
var
  P: string;
begin
  P := ExpandConstant('{pf64}\Microsoft\Edge\Application\msedge.exe');
  if FileExists(P) then begin Result := P; Exit; end;
  P := ExpandConstant('{pf}\Microsoft\Edge\Application\msedge.exe');
  if FileExists(P) then begin Result := P; Exit; end;
  Result := '';
end;

function EdgeExeOk: Boolean;
begin
  Result := (GetEdgeExe('') <> '') and IsTaskSelected('edgeload');
end;
