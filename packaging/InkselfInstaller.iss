; Generated payload is an explicit, checksum-verified list. Never use Source: *.
#ifndef FileListPath
  #error FileListPath must point to the generated allowlist.
#endif
#ifndef BuildOutput
  #error BuildOutput must be supplied by scripts/build_installer.py.
#endif
#ifndef SetupBaseName
  #define SetupBaseName "Inkself-Setup"
#endif
#ifndef AppVersion
  #define AppVersion "0.3.2"
#endif

[Setup]
AppId={{63B179DF-1D43-47EC-BCC4-FB3EE01AFCA1}
AppName=Inkself
AppVersion={#AppVersion}
AppPublisher=Inkself
AppPublisherURL=https://github.com/Ruoyu-Tianyi/inkself
DefaultDirName={localappdata}\Programs\Inkself
DefaultGroupName=Inkself
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DisableProgramGroupPage=yes
DisableWelcomePage=no
WizardStyle=modern
UsePreviousAppDir=yes
UninstallDisplayIcon={app}\Inkself.exe
OutputDir={#BuildOutput}
OutputBaseFilename={#SetupBaseName}
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
SetupMutex=Inkself-Setup
ChangesAssociations=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[LangOptions]
LanguageName=简体中文
LanguageID=$0804
DialogFontName=Microsoft YaHei UI
DialogFontSize=9

[Messages]
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonCancel=取消
ButtonFinish=完成(&F)
WelcomeLabel1=欢迎安装 Inkself
#ifdef OfflineModel
WelcomeLabel2=Inkself 将安装到当前用户的个人程序目录，无需管理员权限。%n%n本安装包包含本机离线内部测试使用的固定 AI 模型，不作为公开模型再分发版本。%n%n字迹档案、样本、作品和模型保存在个人应用数据目录。卸载程序时会保留这些数据；安装器只修复清单中指定的模型资产。
#else
WelcomeLabel2=Inkself 将安装到当前用户的个人程序目录，无需管理员权限。%n%n字迹档案、样本、作品和模型保存在个人应用数据目录。升级或卸载程序时会保留这些数据。%n%n首次使用少样本模型时，请在应用中准备模型；基础安装器不包含模型权重。
#endif
FinishedHeadingLabel=Inkself 安装完成
FinishedLabel=现在可以启动 Inkself。%n%n你的字迹与作品只保存在本机。卸载程序会保留个人数据和已准备的模型。

[CustomMessages]
DesktopShortcut=创建桌面快捷方式
LaunchInkself=启动 Inkself

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; Flags: unchecked

[Dirs]
Name: "{localappdata}\Inkself\data"; Flags: uninsneveruninstall

[Files]
#include FileListPath

[Icons]
Name: "{userprograms}\Inkself\Inkself"; Filename: "{app}\Inkself.exe"; WorkingDir: "{app}"
Name: "{userprograms}\Inkself\卸载 Inkself"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Inkself"; Filename: "{app}\Inkself.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Inkself.exe"; Description: "{cm:LaunchInkself}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

; There are intentionally no Registry, InstallDelete or UninstallDelete entries.
; Models, profiles and documents in LocalAppData must survive uninstallation.
