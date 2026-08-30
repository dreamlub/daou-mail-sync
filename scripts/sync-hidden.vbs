Option Explicit

Dim fileSystem, shell, scriptPath, command, exitCode

Set fileSystem = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptPath = fileSystem.BuildPath(fileSystem.GetParentFolderName(WScript.ScriptFullName), "sync.ps1")
command = "powershell.exe -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & scriptPath & """"
exitCode = shell.Run(command, 0, True)

WScript.Quit exitCode
