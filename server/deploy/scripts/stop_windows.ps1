$ErrorActionPreference = "Stop"
$DeployDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $DeployDir
docker compose --env-file .env -f compose.windows.yml down
