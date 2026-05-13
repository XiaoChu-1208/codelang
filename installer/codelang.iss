; ============================================================
;  codelang Windows installer  (Inno Setup 6)
;
;  Build:
;    1. py tools\build_installer_assets.py   ; regenerates wizard BMPs
;    2. "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\codelang.iss
;  Or just run: installer\build.bat
;
;  Source file is UTF-8 with BOM so Chinese strings render correctly.
; ============================================================

#define MyAppName          "codelang"
#define MyAppNameCN        "懂网"
#define MyAppVersion       "0.1.0"
#define MyAppPublisher     "XiaoChu-1208"
#define MyAppURL           "https://github.com/XiaoChu-1208/codelang"
#define MyAppExeArgs       "-m desktop.app"

[Setup]
; Stable UUID — never regenerate, this is the upgrade key
AppId={{F7F9C2A6-3B57-4DA0-B9C1-7E2F8D5A41C0}
AppName={#MyAppName}
AppVerName={#MyAppName} {#MyAppVersion}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
VersionInfoProductName={#MyAppName}
VersionInfoDescription=codelang - 划词解释代码黑话
VersionInfoVersion={#MyAppVersion}

DefaultDirName={userpf}\codelang
DefaultGroupName=codelang
DisableProgramGroupPage=yes
DisableDirPage=no

; Per-user install — matches existing install.bat behavior (HKCU PATH, %USERPROFILE%\Desktop shortcut)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=codelang-{#MyAppVersion}-setup

; -------- visuals --------
SetupIconFile=..\assets\logo\icon.ico
UninstallDisplayIcon={app}\assets\logo\icon.ico
UninstallDisplayName={#MyAppName} {#MyAppVersion}
WizardImageFile=wizard-large.bmp
WizardSmallImageFile=wizard-small.bmp
WizardStyle=modern
WizardImageAlphaFormat=defined
ShowLanguageDialog=auto

; -------- packaging --------
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "zh"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
zh.IconComment=按住 Alt 划词，立刻弹出代码黑话解释
en.IconComment=Hold Alt + drag to explain code jargon
zh.LaunchAppDesc=立刻启动 codelang
en.LaunchAppDesc=Launch codelang now
zh.StartupTask=开机自启 codelang
en.StartupTask=Start codelang when Windows starts
zh.AddPathTask=把 codelang / dongwang 命令加到 PATH（任意 CMD 直接键入即可启动）
en.AddPathTask=Add codelang / dongwang to PATH (run from any CMD window)
zh.NoPython=检测不到 Python (py 启动器)。codelang 需要 Python 3.10+，请先安装：%nhttps://www.python.org/downloads/%n%n你可以先继续安装，等装好 Python 后再用桌面快捷方式启动 codelang。是否继续？
en.NoPython=Python (py launcher) was not detected. codelang requires Python 3.10+:%nhttps://www.python.org/downloads/%n%nYou can continue and install Python later. Continue?
zh.OtherOptions=其他选项：
en.OtherOptions=Additional options:
zh.PipInstallStatus=正在装 codelang 运行所需的 Python 包（首次需要从 PyPI 下载几个包）...
en.PipInstallStatus=Installing Python dependencies for codelang (one-time download from PyPI)...

[Tasks]
Name: "startupicon"; Description: "{cm:StartupTask}"; GroupDescription: "{cm:OtherOptions}"; Flags: unchecked
Name: "addtopath";   Description: "{cm:AddPathTask}"; GroupDescription: "{cm:OtherOptions}"

[Files]
Source: "..\bin\*";               DestDir: "{app}\bin";               Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\desktop\*";           DestDir: "{app}\desktop";           Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc"
Source: "..\dict\*";              DestDir: "{app}\dict";              Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc"
Source: "..\assets\*";            DestDir: "{app}\assets";            Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\tools\*";             DestDir: "{app}\tools";             Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,seeds\__pycache__\*"
Source: "..\docs\*";              DestDir: "{app}\docs";              Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\extension-browser\*"; DestDir: "{app}\extension-browser"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md";           DestDir: "{app}";                   Flags: ignoreversion
Source: "..\LICENSE";             DestDir: "{app}";                   Flags: ignoreversion
Source: "..\AGENTS.md";           DestDir: "{app}";                   Flags: ignoreversion
Source: "..\CITATION.cff";        DestDir: "{app}";                   Flags: ignoreversion
Source: "..\requirements.txt";    DestDir: "{app}";                   Flags: ignoreversion
Source: "..\llms.txt";            DestDir: "{app}";                   Flags: ignoreversion
Source: "..\install.bat";         DestDir: "{app}";                   Flags: ignoreversion
Source: "..\uninstall.bat";       DestDir: "{app}";                   Flags: ignoreversion

[Icons]
; Shortcuts launch via wscript.exe → codelang_launcher.vbs, NOT pythonw directly.
; The VBS launcher first checks if Python is installed; if not it shows a
; MsgBox offering winget install or a download link. With a direct pythonw
; target, missing-Python failures are silent.

; Start Menu (always)
Name: "{userprograms}\{#MyAppName}\codelang"; \
  Filename: "wscript.exe"; Parameters: """{app}\bin\codelang_launcher.vbs"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\assets\logo\icon.ico"; \
  Comment: "{cm:IconComment}"
Name: "{userprograms}\{#MyAppName}\卸载 codelang"; Filename: "{uninstallexe}"

; Desktop shortcut — always created per user's explicit request
Name: "{userdesktop}\codelang"; \
  Filename: "wscript.exe"; Parameters: """{app}\bin\codelang_launcher.vbs"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\assets\logo\icon.ico"; \
  Comment: "{cm:IconComment}"

; Startup folder shortcut (optional)
Name: "{userstartup}\codelang"; \
  Filename: "wscript.exe"; Parameters: """{app}\bin\codelang_launcher.vbs"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\assets\logo\icon.ico"; \
  Tasks: startupicon

[Run]
; First: pip-install the Python deps so the app can actually start.
; Without this step the shortcut "doesn't open" because mouse/pyperclip/etc
; aren't on the user's Python. Skipped silently if Python isn't installed
; (the launcher VBS will catch that case at click time and guide the user).
Filename: "{cmd}"; \
  Parameters: "/C py -m pip install --user --disable-pip-version-check -r ""{app}\requirements.txt"""; \
  WorkingDir: "{app}"; StatusMsg: "{cm:PipInstallStatus}"; \
  Flags: runhidden; Check: HavePython

; Then launch the app via the VBS launcher (handles missing-Python edge case).
Filename: "wscript.exe"; Parameters: """{app}\bin\codelang_launcher.vbs"""; \
  WorkingDir: "{app}"; Description: "{cm:LaunchAppDesc}"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Best effort: kill running instance before uninstall so files aren't locked
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM pythonw.exe /FI ""WINDOWTITLE eq codelang*"""; Flags: runhidden; RunOnceId: "killpythonw"

[Code]
const
  EnvironmentKey = 'Environment';

var
  CachedPythonw: String;

function FindPythonw(): String;
var
  ResultCode: Integer;
  TmpFile: String;
  Lines: TArrayOfString;
  Line: String;
begin
  Result := '';
  TmpFile := ExpandConstant('{tmp}\pyw_path.txt');
  // Ask py launcher to print pythonw.exe sitting next to the active python.exe
  if Exec(ExpandConstant('{cmd}'),
          '/C py -c "import sys,os;p=os.path.join(os.path.dirname(sys.executable),''pythonw.exe'');print(p if os.path.exists(p) else '''')" > "' + TmpFile + '" 2>&1',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if (ResultCode = 0) and LoadStringsFromFile(TmpFile, Lines) and (GetArrayLength(Lines) > 0) then
    begin
      Line := Trim(Lines[0]);
      if (Line <> '') and FileExists(Line) then
      begin
        Result := Line;
        Exit;
      end;
    end;
  end;
end;

function GetPythonwPath(Param: String): String;
begin
  if CachedPythonw = '' then
  begin
    CachedPythonw := FindPythonw();
    if CachedPythonw = '' then
      // Fallback: rely on PATH at click time. Shortcut will still work if user
      // installs Python afterwards (Windows resolves bare exe names via PATH).
      CachedPythonw := 'pythonw.exe';
  end;
  Result := CachedPythonw;
end;

function HavePython(): Boolean;
begin
  // Gates the [Run] pip-install step: only run it if py launcher is present.
  // If Python isn't installed, skip silently — the VBS launcher will prompt
  // the user to install Python when they click the shortcut.
  Result := FindPythonw() <> '';
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if FindPythonw() = '' then
  begin
    if MsgBox(ExpandConstant('{cm:NoPython}'), mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;

// ---------- PATH helpers (HKCU\Environment) ----------

function NormalizedPath(P: String): String;
begin
  Result := Lowercase(Trim(P));
  while (Length(Result) > 0) and (Result[Length(Result)] = '\') do
    Result := Copy(Result, 1, Length(Result) - 1);
end;

procedure EnvAddPath(NewPath: String);
var
  CurrentPath, NormNew: String;
  Parts: TArrayOfString;
  i, n: Integer;
  Found: Boolean;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', CurrentPath) then
    CurrentPath := '';
  NormNew := NormalizedPath(NewPath);
  // Split on ';' manually
  n := 0;
  SetArrayLength(Parts, 0);
  while Length(CurrentPath) > 0 do
  begin
    i := Pos(';', CurrentPath);
    if i = 0 then
    begin
      SetArrayLength(Parts, n + 1);
      Parts[n] := CurrentPath;
      n := n + 1;
      Break;
    end
    else
    begin
      SetArrayLength(Parts, n + 1);
      Parts[n] := Copy(CurrentPath, 1, i - 1);
      n := n + 1;
      CurrentPath := Copy(CurrentPath, i + 1, Length(CurrentPath));
    end;
  end;
  Found := False;
  for i := 0 to GetArrayLength(Parts) - 1 do
    if NormalizedPath(Parts[i]) = NormNew then
      Found := True;
  if Found then Exit;

  // Rejoin
  CurrentPath := '';
  for i := 0 to GetArrayLength(Parts) - 1 do
    if Trim(Parts[i]) <> '' then
    begin
      if CurrentPath <> '' then CurrentPath := CurrentPath + ';';
      CurrentPath := CurrentPath + Parts[i];
    end;
  if CurrentPath <> '' then
    CurrentPath := CurrentPath + ';' + NewPath
  else
    CurrentPath := NewPath;
  RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', CurrentPath);
end;

procedure EnvRemovePath(OldPath: String);
var
  CurrentPath, NormOld, Rebuilt: String;
  Parts: TArrayOfString;
  i, n: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', CurrentPath) then
    Exit;
  NormOld := NormalizedPath(OldPath);

  n := 0;
  SetArrayLength(Parts, 0);
  while Length(CurrentPath) > 0 do
  begin
    i := Pos(';', CurrentPath);
    if i = 0 then
    begin
      SetArrayLength(Parts, n + 1);
      Parts[n] := CurrentPath;
      n := n + 1;
      Break;
    end
    else
    begin
      SetArrayLength(Parts, n + 1);
      Parts[n] := Copy(CurrentPath, 1, i - 1);
      n := n + 1;
      CurrentPath := Copy(CurrentPath, i + 1, Length(CurrentPath));
    end;
  end;

  Rebuilt := '';
  for i := 0 to GetArrayLength(Parts) - 1 do
    if (Trim(Parts[i]) <> '') and (NormalizedPath(Parts[i]) <> NormOld) then
    begin
      if Rebuilt <> '' then Rebuilt := Rebuilt + ';';
      Rebuilt := Rebuilt + Parts[i];
    end;
  RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Rebuilt);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('addtopath') then
      EnvAddPath(ExpandConstant('{app}\bin'));
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    EnvRemovePath(ExpandConstant('{app}\bin'));
end;
