; Serato Library Windows installer.
;
; SIGNING HOOK (dormant): this script does not call SignTool.
; scripts/release_sign.py signs the packaged executables and this installer
; when WINDOWS_CERTIFICATE_PFX_BASE64 and WINDOWS_CERTIFICATE_PASSWORD are
; both set. When those secrets are absent, signing is skipped and the
; build stays unsigned. Do not add a SignTool directive here; a missing
; certificate would fail the compile.

#ifndef AppVersion
  #error Pass /DAppVersion= from app_config.APP_VERSION.
#endif
#ifndef SourceDir
  #error Pass /DSourceDir= pointing at the PyInstaller folder.
#endif

[Setup]
AppId={{7F3C1A2E-9B84-4D6F-8C15-2E6A0B9D4F71}
AppName=Serato Library
AppVersion={#AppVersion}
AppPublisher=Serato Library
DefaultDirName={localappdata}\Programs\Serato Library
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=Serato-Library-windows-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Serato Library.exe
CloseApplications=yes
RestartApplications=no

[Files]
; The PyInstaller folder only. This does not copy the Serato library.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: desktopicon; Description: "Add a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Icons]
Name: "{autoprograms}\Serato Library"; Filename: "{app}\Serato Library.exe"
Name: "{autodesktop}\Serato Library"; Filename: "{app}\Serato Library.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Serato Library.exe"; Description: "Open Serato Library"; Flags: nowait postinstall skipifsilent
