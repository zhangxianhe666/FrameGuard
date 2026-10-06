; 帧防 FrameGuard · Windows 安装程序（Inno Setup 6）
;
; 用法（在仓库根目录）：
;     iscc /DAppVersion=1.0.0 packaging\windows\frameguard.iss
;
; 注意：Inno Setup 里 SourceDir / OutputDir / 图标等相对路径是相对「脚本所在目录」
; 解析的，不是当前工作目录，所以这里统一用 ISPP 的 SourcePath 拼出绝对路径，
; 保证无论从哪里调用都能找到 dist 与 assets。
;
; 本脚本刻意只用 ASCII（界面文案为英文），避免不同区域设置下的编码歧义。

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName "FrameGuard"
#define AppPublisher "zhangxianhe666"
#define AppURL "https://github.com/zhangxianhe666/FrameGuard"

; SourcePath 是脚本所在目录（带结尾反斜杠）
#define RepoRoot SourcePath + "..\..\"

#ifndef SourceDir
  #define SourceDir RepoRoot + "dist\FrameGuard"
#endif
#ifndef OutputDir
  #define OutputDir RepoRoot + "installer"
#endif
#ifndef IconFile
  #define IconFile RepoRoot + "packaging\assets\frameguard.ico"
#endif
#ifndef ReadmeFile
  #define ReadmeFile RepoRoot + "packaging\windows\README-WINDOWS.txt"
#endif

[Setup]
AppId={{8F3C2A54-6B1D-4E77-9C4A-2D5E7F1B0A93}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\FrameGuard
DefaultGroupName=FrameGuard
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=FrameGuard-{#AppVersion}-windows-x64-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\FrameGuard.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 免管理员安装：默认装到用户目录，必要时用户也可在向导里选择为所有用户安装
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ReadmeFile}"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\FrameGuard"; Filename: "{app}\FrameGuard.exe"
Name: "{group}\Stop FrameGuard"; Filename: "{app}\stop-frameguard.bat"
Name: "{autodesktop}\FrameGuard"; Filename: "{app}\FrameGuard.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FrameGuard.exe"; Description: "Launch FrameGuard"; Flags: nowait postinstall skipifsilent
