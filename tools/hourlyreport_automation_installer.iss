#ifndef AppVersion
  #error AppVersion must be defined
#endif
#ifndef PayloadDir
  #error PayloadDir must be defined
#endif
#ifndef InstallerOutput
  #error InstallerOutput must be defined
#endif

[Setup]
AppId={{A26780B2-50D6-475D-9EEA-9E22ACB56CE9}
AppName=蚁之力 · 竞价数据自动化
AppVersion={#AppVersion}
AppPublisher=蚁之力
DefaultDirName={localappdata}\Programs\Hourlyreport Automation
DefaultGroupName=蚁之力 · 竞价数据自动化
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
MinVersion=10.0
WizardStyle=modern
SetupIconFile={#PayloadDir}\assets\app_icon.ico
UninstallDisplayIcon={app}\hourlyreport_automation.exe
OutputDir={#InstallerOutput}
OutputBaseFilename=Hourlyreport_automation_setup_v{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes

[Languages]
Name: "chinesesimp"; MessagesFile: ".\third_party\ChineseSimplified.isl"

[Dirs]
Name: "{app}\logs"; Flags: uninsneveruninstall
Name: "{app}\reports"; Flags: uninsneveruninstall
Name: "{app}\backups"; Flags: uninsneveruninstall
Name: "{app}\kst_exports"; Flags: uninsneveruninstall

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "configs\*,secrets\*,logs\*,reports\*,backups\*,kst_exports\*"
Source: "{#PayloadDir}\configs\*"; DestDir: "{app}\configs"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist uninsneveruninstall
Source: "{#PayloadDir}\secrets\*"; DestDir: "{app}\secrets"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\蚁之力 · 竞价数据自动化"; Filename: "{app}\hourlyreport_automation.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\蚁之力 · 竞价数据自动化"; Filename: "{app}\hourlyreport_automation.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\hourlyreport_automation.exe"; Description: "启动蚁之力 · 竞价数据自动化"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
