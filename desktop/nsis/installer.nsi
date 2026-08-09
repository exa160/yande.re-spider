; desktop/nsis/installer.nsi
; NSIS 安装脚本 - Yande Spider
;
; 构建：
;   python desktop/build/build_installer.py
; 依赖：NSIS 3.x（https://nsis.sourceforge.io/），把 makensis.exe 加到 PATH
;
; 入口设计：
;   - per-user 安装（RequestExecutionLevel user），无需管理员
;   - 默认安装目录：%LOCALAPPDATA%\Programs\Yande Spider
;   - 自定义下载路径页 + 写注册表 HKCU\Software\Yande Spider\DownloadPath
;   - 卸载时询问是否清理用户数据

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"

!define APP_NAME "Yande Spider"
!define APP_EXE "yande-spider.exe"
!define APP_UNINSTALL "uninstall.exe"
!define APP_VERSION "1.1.9"
!define APP_PUBLISHER "exa160"
!define APP_COPYRIGHT "MIT License"
!define MUI_ABORTWARNING

; 默认安装目录（per-user，无需管理员）
InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}"
InstallDirRegKey HKCU "Software\${APP_NAME}" "InstallDir"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "YandeSpider-Setup-v${APP_VERSION}.exe"
RequestExecutionLevel user

; MUI 设置
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Header\nsis3-branding\win.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Wizard\win.bmp"
!define MUI_WELCOMEPAGE_TITLE "${APP_NAME} 安装向导"
!define MUI_FINISHPAGE_TITLE "${APP_NAME} 安装完成"
!define MUI_FINISHPAGE_RUN "${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 ${APP_NAME}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "license.txt"
Page custom DownloadPathPage DownloadPathPageLeave
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "SimpChinese"

Var DownloadPath

; 下载路径选择页
Function DownloadPathPage
  ; 默认下载路径：安装目录下的 downloads
  StrCpy $DownloadPath "$INSTDIR\downloads"

  nsDialogs::Create /NOUNLOAD 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}

  nsDialogs::CreateControl /NOUNLOAD "STATIC" 0 0 0 100% 12u "下载目录（默认在安装目录下，建议改到大容量磁盘）"
  nsDialogs::CreateControl /NOUNLOAD "EDIT" 0 0 14u 100% 12u "$DownloadPath"
  Pop $1
  nsDialogs::CreateControl /NOUNLOAD "BUTTON" 0 75% 30u 25% 12u "浏览..."
  Pop $2
  nsDialogs::Show
FunctionEnd

Function DownloadPathPageLeave
  nsDialogs::GetControlText $1 $DownloadPath
  ; 简单校验：路径必须非空
  ${If} $DownloadPath == ""
    MessageBox MB_ICONSTOP "下载路径不能为空"
    Abort
  ${EndIf}
FunctionEnd

; 安装前检查
Function .onInit
  ; 检查是否已有实例在运行（通过 lock 端口 47299）
  nsExec::ExecToLog 'netstat -ano | findstr :47299'
  Pop $0
  ${If} $0 == 0
    MessageBox MB_ICONSTOP "检测到 ${APP_NAME} 正在运行，请先关闭后再安装。"
    Abort
  ${EndIf}
FunctionEnd

Section "主程序" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  ; 复制 PyInstaller 产物
  File /r "dist\yande-spider\_internal"
  File "dist\yande-spider\${APP_EXE}"

  ; 写下载路径到注册表（首次启动时读取）
  WriteRegStr HKCU "Software\${APP_NAME}" "DownloadPath" "$DownloadPath"
  WriteRegStr HKCU "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\${APP_NAME}" "Version" "${APP_VERSION}"

  ; 写卸载程序
  WriteUninstaller "$INSTDIR\${APP_UNINSTALL}"
SectionEnd

Section "开始菜单快捷方式"
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\卸载.lnk" "$INSTDIR\${APP_UNINSTALL}"
SectionEnd

Section "桌面快捷方式"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "Uninstall"
  ; 询问是否保留用户数据
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除用户数据目录（%APPDATA%\yande-spider）和下载目录？$\r$\n选否则保留。" IDNO skip_data
    RMDir /r "$APPDATA\yande-spider"
    RMDir /r "$DownloadPath"
  skip_data:
  ; 删除应用目录
  RMDir /r "$INSTDIR"
  ; 清理注册表
  DeleteRegKey HKCU "Software\${APP_NAME}"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName"
  ; 删除快捷方式
  RMDir /r "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"
SectionEnd
