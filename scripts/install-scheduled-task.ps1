$ErrorActionPreference = "Stop"

$hiddenLauncher = Join-Path $PSScriptRoot "sync-hidden.vbs"
$wscript = Join-Path $env:SystemRoot "System32\wscript.exe"
$taskName = "Daou Mail Sync to Gmail"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$action = New-ScheduledTaskAction `
    -Execute $wscript `
    -Argument "`"$hiddenLauncher`""
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 10)
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Copy new DaouOffice mail into tony.waldlust@gmail.com every 10 minutes without showing a console window." `
    -Force | Out-Null

Write-Output "Installed scheduled task: $taskName"
