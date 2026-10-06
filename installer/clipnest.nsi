!ifndef APP_VERSION
  !define APP_VERSION "0.2.1"
!endif

Unicode true
Name "Clipnest"
OutFile "..\dist\Clipnest_${APP_VERSION}_x64-setup.exe"
InstallDir "$LOCALAPPDATA\Programs\Clipnest"
RequestExecutionLevel user
SetCompressor /SOLID lzma

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Clipnest" MainSection
  SetOutPath "$INSTDIR"
  File /r "..\dist\Clipnest\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Clipnest"
  CreateShortcut "$SMPROGRAMS\Clipnest\Clipnest.lnk" "$INSTDIR\Clipnest.exe"
  CreateShortcut "$SMPROGRAMS\Clipnest\Uninstall Clipnest.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Clipnest" "DisplayName" "Clipnest"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Clipnest" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Clipnest" "UninstallString" '"$INSTDIR\Uninstall.exe"'
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\Clipnest\Clipnest.lnk"
  Delete "$SMPROGRAMS\Clipnest\Uninstall Clipnest.lnk"
  RMDir "$SMPROGRAMS\Clipnest"
  Delete "$INSTDIR\Clipnest.exe"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Clipnest"
SectionEnd
