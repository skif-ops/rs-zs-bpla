$ErrorActionPreference = "Stop"
$DeployDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $DeployDir
New-Item -ItemType Directory -Force -Path "..\data", "..\output" | Out-Null
docker compose --env-file .env -f compose.windows.yml build --pull
docker compose --env-file .env -f compose.windows.yml up -d
docker compose --env-file .env -f compose.windows.yml ps
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/health | Out-Null
Write-Host "Muhoed is available at http://127.0.0.1:8000"
