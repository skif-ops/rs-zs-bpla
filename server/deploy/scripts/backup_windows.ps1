# Backup of the Muhoed server data and output (docs/SERVER_RETENTION_2026-10-03.md).  station/backup.py runs inside
# the server container: it copies every SQLite database with the SQLite backup API (a consistent snapshot while the
# server and the bridges write; a zip of the live file with its WAL is not) and packs data (audio included) and
# output into one zip.  With the server down the image is run once for the same job.
param([string]$Destination = "")
$ErrorActionPreference = "Stop"
$DeployDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ServerRoot = (Resolve-Path (Join-Path $DeployDir "..")).Path
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
if (-not $Destination) { $Destination = Join-Path $ServerRoot ("backup_" + $Stamp + ".zip") }
Set-Location $DeployDir
$Compose = @("compose", "--env-file", ".env", "-f", "compose.windows.yml")
$Inside = "/app/output/backups/backup_$Stamp.zip"
New-Item -ItemType Directory -Force -Path (Join-Path $ServerRoot "output\backups") | Out-Null
$Running = & docker @Compose ps -q server 2>$null
if ($Running) {
    & docker @Compose exec -T server python -m station.backup --out $Inside
} else {
    & docker @Compose run --rm --no-deps -T server python -m station.backup --out $Inside
}
if ($LASTEXITCODE -ne 0) { throw "backup failed" }
Move-Item -Force (Join-Path $ServerRoot ("output\backups\backup_" + $Stamp + ".zip")) $Destination
Write-Host "Backup saved: $Destination"
