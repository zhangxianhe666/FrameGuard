; 帧防 FrameGuard · Windows 安装脚本（Inno Setup 6）
;
; 用法（在仓库根目录执行）：
;   iscc /DAppVersion=1.0.0 /DSourceDir=dist\FrameGuard /DOutputDir=installer packaging\windows\frameguard.iss
;
; 说明：本文件刻意只用 ASCII 字符，避免不同区域设置下编译器的编码歧义；
;       面向用户的界面文案为英文，程序内部界面仍是中文。

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\FrameGuard"
#endif
#ifndef OutputDir
  #define OutputDir "installer"
#endif
#ifndef IconFile
  #define IconFile "packaging\assets\frameguard.ico"
#endif

#define AppName "FrameGuard"
#define AppPublisher "zhangxianhe666"
#define AppURL "https://github.com/zhangxianhe666/FrameGuard"

[Setup]
; AppId 一经发布不可更改，否则会被识别为另一个程序
AppId={{8F3C2A54-6B1D-4E77-9C4A-2D5E7F1B0A93}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
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
; 允许普通用户免管理员安装；需要装到 Program Files 时会自动请求提权
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

[Icons]
Name: "{group}\FrameGuard"; Filename: "{app}\FrameGuard.exe"
Name: "{group}\Stop FrameGuard"; Filename: "{app}\stop-frameguard.bat"; IconFilename: "{app}\FrameGuard.exe"
Name: "{autodesktop}\FrameGuard"; Filename: "{app}\FrameGuard.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FrameGuard.exe"; Description: "Launch FrameGuard"; Flags: nowait postinstall skipifsilent
