' Launch codelang desktop app in background with no console window.
' Double-click to start. App lives in system tray.
Set objShell = CreateObject("WScript.Shell")
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
strProjectRoot = CreateObject("Scripting.FileSystemObject").GetParentFolderName(strPath)
objShell.CurrentDirectory = strProjectRoot
objShell.Run "pythonw -m desktop.app", 0, False
