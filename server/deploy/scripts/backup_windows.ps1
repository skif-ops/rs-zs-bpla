param([string]$Destination = "")
$ErrorActionPreference = "Stop"
$ServerRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $Destination) { $Destination = Join-Path $ServerRoot ("backup_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".zip") }
Compress-Archive -Path (Join-Path $ServerRoot "data"), (Join-Path $ServerRoot "output") -DestinationPath $Destination -Force
Write-Host "Backup saved: $Destination"
