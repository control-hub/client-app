; Inno Setup script for ControlHub installer

#define MyAppName "ControlHub"
#define MyAppVersion "1.5.6"
#define MyAppPublisher "lixelv"
#define MyAppURL "https://control-hub.org"
#define MyAppExeName "ControlHub.exe"
#define MyAppIcon "logo.ico"

[Setup]
AppId={{CONTROLHUB-UNIQUE-ID}}
AppName={#MyAppName}
AppVerName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=../LICENSE
OutputDir=installer
OutputBaseFilename=ControlHub_Setup_{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppIcon}
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "install.bat"; DestDir: "{app}"
Source: "ControlHub.exe"; DestDir: "{app}"
Source: "requirements.txt"; DestDir: "{app}"
Source: "uninstall.bat"; DestDir: "{app}"
Source: "python/*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs
Source: "logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "../.gitignore"; DestDir: "{app}"; Flags: ignoreversion
Source: "../LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "../README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIcon}"
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\install.bat"; Description: "Run installation script"; Flags: postinstall runascurrentuser runhidden

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c {app}\uninstall.bat"; WorkingDir: "{app}"; Flags: runhidden

[Code]
var
  DomainPage, TokenPage: TInputQueryWizardPage;
  ServerURL, UserToken: String;

procedure InitializeWizard;
begin
  DomainPage := CreateInputQueryPage(wpWelcome,
    'API Server URL', 'Specify the ControlHub API server URL',
    'Default is https://pb.control-hub.org. You may enter a custom domain:');
  DomainPage.Add('Server URL:', False);
  DomainPage.Values[0] := 'https://pb.control-hub.org';

  TokenPage := CreateInputQueryPage(DomainPage.ID,
    'Token Entry', 'Enter your ControlHub access token',
    'Provide the token for ' + DomainPage.Values[0] + ':');
  TokenPage.Add('Access Token:', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  RespText: String;
  WinHttp: Variant;
begin
  Result := True;

  if CurPageID = DomainPage.ID then
  begin
    ServerURL := Trim(DomainPage.Values[0]);
    if (ServerURL = '') or ((Pos('http://', LowerCase(ServerURL)) <> 1) and (Pos('https://', LowerCase(ServerURL)) <> 1)) then
    begin
      MsgBox('Please enter a valid URL starting with http:// or https://', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end
  else if CurPageID = TokenPage.ID then
  begin
    UserToken := Trim(TokenPage.Values[0]);
    if UserToken = '' then
    begin
      MsgBox('Token cannot be empty.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    try
      WinHttp := CreateOleObject('WinHttp.WinHttpRequest.5.1');
      WinHttp.Open('GET', ServerURL + '/api/collections/computers/records?token=' + UserToken, False);
      WinHttp.Send('');
      RespText := WinHttp.ResponseText;
      if Pos('"totalItems":0', RespText) > 0 then
      begin
        MsgBox('Invalid token for ' + ServerURL, mbError, MB_OK);
        Result := False;
        Exit;
      end;
    except
      MsgBox('Cannot connect to ' + ServerURL + '. Check your network and URL.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    SaveStringToFile(ExpandConstant('{app}\.env'),
      'CONTROLHUB_SERVER_URL=' + ServerURL + #13#10 +
      'TOKEN=' + UserToken,
      False);
  end;
end;

procedure DeinitializeUninstall;
var
  ExitCode: Integer;
begin
  Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
end;
