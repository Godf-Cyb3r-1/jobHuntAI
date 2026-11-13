#define MyAppName "JobHuntAI"
#define MyAppVersion "0.2.0"
[Setup]
AppId={{B64E86EE-82F4-4A50-9875-7EAE37034E19}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=JobHuntAI Community
DefaultDirName={autopf}\JobHuntAI
DefaultGroupName={#MyAppName}
OutputDir=dist-install
OutputBaseFilename=JobHuntAI-Setup-Windows-x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\JobHuntAI.exe
SetupLogging=yes

[Files]
Source: "package\JobHuntAI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "package\start-server.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "package\start-server.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "package\install-windows.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "package\uninstall-windows.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "package\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "package\opencode.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install-windows.ps1"""; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN JobHuntAI"; Flags: runhidden
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN JobHuntAI /F"; Flags: runhidden