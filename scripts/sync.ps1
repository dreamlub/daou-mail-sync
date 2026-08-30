$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$logDirectory = Join-Path $projectRoot "data"
$logFile = Join-Path $logDirectory "sync.log"

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$env:DAOU_IMAP_USER = "tony@waldlust.co.kr"

Push-Location $projectRoot
try {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $output = & $python -m daou_mail_sync.cli sync --apply --yes 2>&1
    $exitCode = $LASTEXITCODE
    "[$timestamp] exit=$exitCode $($output -join ' ')" | Add-Content -Path $logFile -Encoding UTF8
    exit $exitCode
}
finally {
    Pop-Location
}
