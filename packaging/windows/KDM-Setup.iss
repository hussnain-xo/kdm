; Kalupura Download Manager — Windows installer (Inno Setup 6+)
; https://jrsoftware.org/isinfo.php
; Build: ISCC.exe /DMyAppVersion=X.Y.Z packaging\windows\KDM-Setup.iss
;
; Includes optional ExtensionInstallForcelist (Chrome + Edge) for local .crx — no Web Store.
; Optional: dist\extensions\KDM-extension.crx for Chrome/Edge policy task (skipifsourcedoesntexist).

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "Kalupura Download Manager"
; Extension ID + version: must match manifest (key → ID) and scripts (CRX pack).
; See [Code] const KDM_EXT_ID / KDM_EXT_VER — keep in sync when bumping manifest.

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
Name: "policyext"; Description: "Register KDM extension without Web Store (Chrome/Edge policy — close all browser windows after setup, then reopen; like IDM local integration)"; GroupDescription: "Browser integration:"; Flags: checkedonce
Name: "chromeload"; Description: "Also start Chrome with extension for this session only (--load-extension)"; GroupDescription: "Browser integration:"; Flags: unchecked
Name: "edgeload"; Description: "Also start Edge with extension for this session only"; GroupDescription: "Browser integration:"; Flags: unchecked
Name: "extwizard"; Description: "Show manual «Load unpacked» help (folder + tabs)"; GroupDescription: "Browser integration:"; Flags: unchecked

[Files]
Source: "..\..\dist\KDM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\dist\extensions\KDM-extension.crx"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\KDM.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\KDM.exe"; Tasks: desktopicon

[Run]
Filename: "{code:GetChromeExe}"; Parameters: "--load-extension=""{app}\browser-extension"""; Flags: nowait postinstall skipifsilent shellexec; Tasks: chromeload; Check: ChromeExeOk

Filename: "{code:GetEdgeExe}"; Parameters: "--load-extension=""{app}\browser-extension"""; Flags: nowait postinstall skipifsilent shellexec; Tasks: edgeload; Check: EdgeExeOk

Filename: "{app}\KDM.exe"; Parameters: "--install-browser-extension"; StatusMsg: "Opening KDM browser extension helper…"; Flags: postinstall skipifsilent waituntilterminated; Tasks: extwizard

Filename: "{app}\KDM.exe"; Parameters: "--post-install"; Description: "Launch Kalupura Download Manager"; Flags: nowait postinstall skipifsilent

[Code]
const
  KDM_POLICY_VALUENAME = 'KDMKalupura';
  KDM_EXT_ID = 'pgpagjhonmkkgcgkbgkphbabhbnkdlpd';
  KDM_EXT_VER = '1.4.0';

function FileUrlFromWinPath(const P: string): string;
var
  s: string;
begin
  s := P;
  StringChange(s, '\', '/');
  StringChange(s, ' ', '%20');
  if (Length(s) >= 2) and (s[2] = ':') then
    Result := 'file:///' + Copy(s, 1, 1) + ':' + Copy(s, 3, MaxInt)
  else
    Result := 'file:///' + s;
end;

procedure WritePolicyFilesAndRegistry;
var
  AppDir, XmlPath, CrxPath, CrxUrl, XmlUrl, RegVal, XmlBody: string;
begin
  if not IsTaskSelected('policyext') then
    Exit;
  AppDir := ExpandConstant('{app}');
  CrxPath := AppDir + '\KDM-extension.crx';
  if not FileExists(CrxPath) then
    Exit;
  XmlPath := AppDir + '\extension-policy\updates.xml';
  if not DirExists(AppDir + '\extension-policy') then
    if not CreateDir(AppDir + '\extension-policy') then
      Exit;
  CrxUrl := FileUrlFromWinPath(CrxPath);
  XmlUrl := FileUrlFromWinPath(XmlPath);
  XmlBody :=
    '<?xml version="1.0" encoding="UTF-8"?>' + #13#10 +
    '<gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">' + #13#10 +
    '  <app appid="' + KDM_EXT_ID + '">' + #13#10 +
    '    <updatecheck codebase="' + CrxUrl + '" version="' + KDM_EXT_VER + '" />' + #13#10 +
    '  </app>' + #13#10 +
    '</gupdate>' + #13#10;
  if not SaveStringToFile(XmlPath, XmlBody, False) then
    Exit;
  RegVal := KDM_EXT_ID + ';' + XmlUrl;
  RegWriteString(HKEY_LOCAL_MACHINE,
    'Software\Policies\Google\Chrome\ExtensionInstallForcelist',
    KDM_POLICY_VALUENAME, RegVal);
  RegWriteString(HKEY_LOCAL_MACHINE,
    'Software\Policies\Microsoft\Edge\ExtensionInstallForcelist',
    KDM_POLICY_VALUENAME, RegVal);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WritePolicyFilesAndRegistry;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  P: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKEY_LOCAL_MACHINE,
      'Software\Policies\Google\Chrome\ExtensionInstallForcelist',
      KDM_POLICY_VALUENAME);
    RegDeleteValue(HKEY_LOCAL_MACHINE,
      'Software\Policies\Microsoft\Edge\ExtensionInstallForcelist',
      KDM_POLICY_VALUENAME);
    P := ExpandConstant('{app}\extension-policy\updates.xml');
    if FileExists(P) then
      DeleteFile(P);
  end;
end;

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
