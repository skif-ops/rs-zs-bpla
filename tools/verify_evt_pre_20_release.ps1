[CmdletBinding()]
param(
    [string]$PackageRoot = (Split-Path -Parent $PSScriptRoot)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    throw $Message
}

function Find-One([string]$Root, [string]$Name) {
    $matches = @(Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object { $_.Name -eq $Name })
    if ($matches.Count -ne 1) {
        Fail "Expected exactly one file named $Name, found $($matches.Count)"
    }
    return $matches[0].FullName
}

try {
    $root = [System.IO.Path]::GetFullPath($PackageRoot)
    $rootPrefix = $root.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    $sumsPath = Join-Path $root "SHA256SUMS.txt"
    $manifestPath = Join-Path $root "release_manifest.json"
    $contractPath = Find-One $root "bench_release_contract_2026111201.json"
    $pendingPath = Find-One $root "HARDWARE_PENDING.json"

    foreach ($required in @($sumsPath, $manifestPath, $contractPath, $pendingPath)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            Fail "Required file is missing: $required"
        }
    }

    $lines = Get-Content -LiteralPath $sumsPath -Encoding UTF8
    if ($lines.Count -eq 0) {
        Fail "SHA256SUMS.txt is empty"
    }

    $checked = 0
    foreach ($line in $lines) {
        if ($line -notmatch "^(?<hash>[0-9a-fA-F]{64})  (?<path>.+)$") {
            Fail "Malformed SHA256SUMS line: $line"
        }
        $expectedHash = $Matches.hash.ToLowerInvariant()
        $relative = $Matches.path
        if ([System.IO.Path]::IsPathRooted($relative) -or $relative -match "(^|/|\\)\.\.($|/|\\)") {
            Fail "Unsafe path in SHA256SUMS.txt: $relative"
        }
        $localRelative = $relative.Replace("/", [System.IO.Path]::DirectorySeparatorChar)
        $fullPath = [System.IO.Path]::GetFullPath((Join-Path $root $localRelative))
        if (-not $fullPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Fail "Path escapes package root: $relative"
        }
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            Fail "File listed in SHA256SUMS.txt is missing: $relative"
        }
        $actual = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expectedHash) {
            Fail "SHA-256 mismatch: $relative"
        }
        $checked += 1
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $contract = Get-Content -LiteralPath $contractPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $pending = Get-Content -LiteralPath $pendingPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $releaseId = "EVT_PRE_20_BENCH_RELEASE_2026111201"

    if ($manifest.release_id -ne $releaseId -or $contract.release_id -ne $releaseId -or $pending.release_id -ne $releaseId) {
        Fail "Release ID mismatch"
    }
    if ($manifest.status -ne "READY_TO_FLASH_HARDWARE_VALIDATION_PENDING") {
        Fail "Unexpected release manifest status: $($manifest.status)"
    }
    if ($pending.status -ne "HARDWARE_VALIDATION_PENDING") {
        Fail "Unexpected hardware status: $($pending.status)"
    }
    if ([bool]$pending.field_lora_profile_in_package -or [bool]$pending.firmware_lock_allowed) {
        Fail "Safety interlock mismatch: field LoRa profile or firmware lock is enabled"
    }

    $expected = @{
        "2026111201.bin" = [string]$contract.stm32.expected_image_sha256
        "zephyr.signed.bin" = [string]$contract.nrf52840.expected_signed_image_sha256
        "merged.hex" = [string]$contract.nrf52840.expected_merged_hex_sha256
        "Dioneya_Commissioning_0.1.1_bench_20261112.apk" = [string]$contract.android.apk_sha256
    }
    foreach ($item in $expected.GetEnumerator()) {
        $filePath = Find-One $root $item.Key
        $actual = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $item.Value.ToLowerInvariant()) {
            Fail "Release contract mismatch: $($item.Key)"
        }
    }

    Write-Host ""
    Write-Host "PASS: package verified" -ForegroundColor Green
    Write-Host "Release: $releaseId"
    Write-Host "Files checked: $checked"
    Write-Host "Status: ready to flash, hardware validation pending"
    exit 0
}
catch {
    Write-Host ""
    Write-Host "FAIL: package verification failed" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
