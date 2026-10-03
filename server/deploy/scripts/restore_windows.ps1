# Restore of the Muhoed server data and output from an archive of backup_windows.ps1 (docs/SERVER_RETENTION_2026-10-03.md).
# Stops the services, runs station/backup.py --restore inside the server image (it refuses an archive that is not a
# server backup or whose databases fail their integrity check, replaces the contents of data and output and keeps
# what it replaced in output/backups/before_restore_<stamp>.tar.gz), then starts the services again whatever happened.
param([Parameter(Mandatory = $true)][string]$Archive)
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) { throw "archive not found: $Archive" }
$Archive = (Resolve-Path -LiteralPath $Archive).Path
$DeployDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ServerRoot = (Resolve-Path (Join-Path $DeployDir "..")).Path
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$Ext = if ($Archive.ToLower().EndsWith(".zip")) { ".zip" } else { ".tar.gz" }
$Inside = "restore_$Stamp$Ext"
Set-Location $DeployDir
$Compose = @("compose", "--env-file", ".env", "-f", "compose.windows.yml")
$Backups = Join-Path $ServerRoot "output\backups"
New-Item -ItemType Directory -Force -Path $Backups | Out-Null
Copy-Item -LiteralPath $Archive -Destination (Join-Path $Backups $Inside)
try {
    & docker @Compose stop
    & docker @Compose run --rm --no-deps -T server python -m station.backup --restore "/app/output/backups/$Inside"
    if ($LASTEXITCODE -ne 0) { throw "restore refused or failed (exit $LASTEXITCODE)" }
    Write-Host "Restored: $Archive"
} finally {
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Backups $Inside)
    & docker @Compose up -d
}
