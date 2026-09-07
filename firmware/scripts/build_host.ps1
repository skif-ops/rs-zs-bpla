$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildDir = Join-Path $RootDir "build-host-v1.2"
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
$Sources = Get-ChildItem (Join-Path $RootDir "src") -Filter *.c | ForEach-Object { $_.FullName }
gcc -std=c11 -Wall -Wextra -Werror -pedantic -I (Join-Path $RootDir "include") -I (Join-Path $RootDir "generated") $Sources (Join-Path $RootDir "tests\test_core.c") -lm -o (Join-Path $BuildDir "zs_core_tests.exe")
& (Join-Path $BuildDir "zs_core_tests.exe")
gcc -std=c11 -Wall -Wextra -Werror -pedantic -I (Join-Path $RootDir "include") -I (Join-Path $RootDir "generated") $Sources (Join-Path $RootDir "tools\emit_detection.c") -lm -o (Join-Path $BuildDir "zs_emit_detection.exe")
& (Join-Path $BuildDir "zs_emit_detection.exe") (Join-Path $BuildDir "detection_v14.cbor")
Write-Host "Host verification PASS"
