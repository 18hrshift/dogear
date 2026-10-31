; Inno Setup script for Dogear's Windows installer. packaging/build.py compiles it with
; ISCC, passing /DAppVersion, /DBundleDir (the frozen dogear folder), /DOutputDir, and
; /DOutputBaseName.
;
; It installs for the current user only (no administrator needed) into
; %LOCALAPPDATA%\Programs\Dogear, adds "Dogear" to the Start menu, and can put the dogear
; command on the user's PATH. The shortcut runs `dogear serve` in a console window: that
; window is Dogear, and closing it stops Dogear. The wizard uses standard Windows
; controls, which screen readers read.

#ifndef AppVersion
  #error Pass /DAppVersion=...
#endif

[Setup]
; Never change AppId: Windows knows the installed app by it.
AppId={{F4E8DE45-B6E1-4C6A-B1AC-902B7088049B}
AppName=Dogear
AppVersion={#AppVersion}
AppPublisher=Dogear contributors
AppPublisherURL=https://github.com/18hrshift/dogear-app
AppSupportURL=https://github.com/18hrshift/dogear-app/issues
DefaultDirName={autopf}\Dogear
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
ChangesEnvironment=yes
UninstallDisplayName=Dogear
UninstallDisplayIcon={app}\dogear.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseName}

[Tasks]
Name: addtopath; Description: "Add the dogear command to PATH, to use it in Command Prompt or PowerShell"; Flags: unchecked
Name: desktopicon; Description: "Add Dogear to the desktop"; Flags: unchecked

[InstallDelete]
; An upgrade replaces the frozen Python folder whole: files an older version had and this
; one doesn't (such as an older package's metadata) must not linger beside the new ones.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Dogear"; Filename: "{app}\dogear.exe"; Parameters: "serve"; WorkingDir: "{userdocs}"; Comment: "Start Dogear. Keep its window open while you use it."
Name: "{autoprograms}\Dogear for phones and tablets"; Filename: "{app}\dogear.exe"; Parameters: "serve --lan"; WorkingDir: "{userdocs}"; Comment: "Start Dogear so phones and tablets on the same network can use it too. Keep its window open while you use it."
Name: "{autodesktop}\Dogear"; Filename: "{app}\dogear.exe"; Parameters: "serve"; WorkingDir: "{userdocs}"; Comment: "Start Dogear. Keep its window open while you use it."; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NotOnPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\dogear.exe"; Parameters: "serve"; WorkingDir: "{userdocs}"; Description: "Start Dogear now"; Flags: postinstall nowait skipifsilent

[Code]
const
  EnvironmentKey = 'Environment';

{ Where Dir is in the user's PATH, as the index of its first character, or 0. }
function PathIndex(Dir: string): Integer;
var
  Paths: string;
begin
  Result := 0;
  if RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';');
end;

function NotOnPath(Dir: string): Boolean;
begin
  Result := PathIndex(Dir) = 0;
end;

{ Take the install folder back off the user's PATH, with the semicolon that joined it. }
procedure RemoveFromPath(Dir: string);
var
  Paths: string;
  Index: Integer;
begin
  Index := PathIndex(Dir);
  if (Index = 0) or not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    exit;
  if Index = 1 then
    Delete(Paths, 1, Length(Dir) + 1)
  else
    Delete(Paths, Index - 1, Length(Dir) + 1);
  RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath(ExpandConstant('{app}'));
end;
