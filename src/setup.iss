; Inno Setup script for ControlHub installer

#define MyAppName "ControlHub"
#define MyAppVersion "1.2.0"
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
Source: "python\*"; DestDir: "{app}\python"
Source: "install.bat"; DestDir: "{app}"
Source: "ControlHub.exe"; DestDir: "{app}"
Source: "requirements.txt"; DestDir: "{app}"
Source: "uninstall.bat"; DestDir: "{app}"
Source: "logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "../.gitignore"; DestDir: "{app}"; Flags: ignoreversion
Source: "../LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "../README.md"; DestDir: "{app}"; Flags: ignoreversion

[Code]
var
  TokenPage: TInputQueryWizardPage;
  ValidToken: String;
  
procedure InitializeWizard;
begin
  TokenPage := CreateInputQueryPage(wpWelcome,
    'Token Validation', 'Enter your token',
    'Please enter your ControlHub token below, then click Next:');
  TokenPage.Add('Token:', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Token: String;
  WinHttpReq: Variant;
  Response: String;
begin
  Result := True;
  
  if CurPageID = TokenPage.ID then
  begin
    Token := TokenPage.Values[0];
    if Token = '' then
    begin
      MsgBox('Please enter a valid token.', mbError, MB_OK);
      Result := False;
      exit;
    end;
    
    try
      // Use Windows COM object to make the HTTP request
      WinHttpReq := CreateOleObject('WinHttp.WinHttpRequest.5.1');
      WinHttpReq.Open('GET', 'https://pb.control-hub.org/api/collections/computers/records?token=' + Token, false);
      WinHttpReq.Send('');
      Response := WinHttpReq.ResponseText;
          
      if Pos('"totalItems":0', Response) > 0 then
      begin
        MsgBox('Invalid token. Please try again.', mbError, MB_OK);
        Result := False;
        exit;
      end;
      
      // Store the valid token to use later
      ValidToken := Token;
    except
      MsgBox('Failed to connect to server. Please check your internet connection and try again.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Create .env file with token after installation is complete
    SaveStringToFile(ExpandConstant('{app}\.env'), 'TOKEN=' + ValidToken, False);
  end;
end;

procedure DeinitializeUninstall;
var
  ResultCode: Integer;
begin
  Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;



[UninstallRun]
Filename: "{cmd}"; Parameters: "/c ""{app}\uninstall.bat"""; WorkingDir: "{app}"; Flags: runhidden

[Run]
Filename: "{app}\install.bat"; Description: "Run installation script"; Flags: postinstall runascurrentuser
