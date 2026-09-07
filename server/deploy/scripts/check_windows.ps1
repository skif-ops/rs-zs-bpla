$ErrorActionPreference = "Stop"
docker version
docker compose version
docker compose -f "$PSScriptRoot\..\compose.windows.yml" config
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
