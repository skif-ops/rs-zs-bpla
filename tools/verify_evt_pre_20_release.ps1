[CmdletBinding()]
param(
    [string]$PackageRoot = (Split-Path -Parent $PSScriptRoot)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    throw $Message
}

try {
    $root = [System.IO.Path]::GetFullPath($PackageRoot)
    $rootPrefix = $root.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    $sumsPath = Join-Path $root "SHA256SUMS.txt"
    $manifestPath = Join-Path $root "release_manifest.json"
    $contractPath = Join-Path $root "05_Релизные_документы\bench_release_contract_2026111201.json"
    $pendingPath = Join-Path $root "05_Релизные_документы\HARDWARE_PENDING.json"

    foreach ($required in @($sumsPath, $manifestPath, $contractPath, $pendingPath)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            Fail "Отсутствует обязательный файл: $required"
        }
    }

    $lines = Get-Content -LiteralPath $sumsPath -Encoding UTF8
    if ($lines.Count -eq 0) {
        Fail "SHA256SUMS.txt пуст"
    }

    $checked = 0
    foreach ($line in $lines) {
        if ($line -notmatch "^(?<hash>[0-9a-fA-F]{64})  (?<path>.+)$") {
            Fail "Ошибочная строка SHA256SUMS.txt: $line"
        }
        $expectedHash = $Matches.hash.ToLowerInvariant()
        $relative = $Matches.path
        if ([System.IO.Path]::IsPathRooted($relative) -or $relative -match "(^|/|\\)\.\.($|/|\\)") {
            Fail "Недопустимый путь в SHA256SUMS.txt: $relative"
        }
        $localRelative = $relative.Replace("/", [System.IO.Path]::DirectorySeparatorChar)
        $fullPath = [System.IO.Path]::GetFullPath((Join-Path $root $localRelative))
        if (-not $fullPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Fail "Путь выходит за границы комплекта: $relative"
        }
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            Fail "Не найден файл из SHA256SUMS.txt: $relative"
        }
        $actual = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expectedHash) {
            Fail "Не совпал SHA-256: $relative"
        }
        $checked += 1
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $contract = Get-Content -LiteralPath $contractPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $pending = Get-Content -LiteralPath $pendingPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $releaseId = "EVT_PRE_20_BENCH_RELEASE_2026111201"

    if ($manifest.release_id -ne $releaseId -or $contract.release_id -ne $releaseId -or $pending.release_id -ne $releaseId) {
        Fail "Не совпал release ID"
    }
    if ($manifest.status -ne "READY_TO_FLASH_HARDWARE_VALIDATION_PENDING") {
        Fail "Неожиданный статус release_manifest.json: $($manifest.status)"
    }
    if ($pending.status -ne "HARDWARE_VALIDATION_PENDING") {
        Fail "Неожиданный статус HARDWARE_PENDING.json: $($pending.status)"
    }
    if ([bool]$pending.field_lora_profile_in_package -or [bool]$pending.firmware_lock_allowed) {
        Fail "Нарушена блокировка: полевой LoRa-профиль или firmware lock не должны входить в стендовый выпуск"
    }

    $expected = @{
        "01_Прошивка_STM32\2026111201.bin" = [string]$contract.stm32.expected_image_sha256
        "02_Прошивка_nRF52840\zephyr.signed.bin" = [string]$contract.nrf52840.expected_signed_image_sha256
        "02_Прошивка_nRF52840\merged.hex" = [string]$contract.nrf52840.expected_merged_hex_sha256
        "03_Приложение_монтажника\Dioneya_Commissioning_0.1.1_bench_20261112.apk" = [string]$contract.android.apk_sha256
    }
    foreach ($item in $expected.GetEnumerator()) {
        $filePath = Join-Path $root $item.Key
        if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
            Fail "Отсутствует файл выпуска: $($item.Key)"
        }
        $actual = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $item.Value.ToLowerInvariant()) {
            Fail "Файл не совпал с релизным контрактом: $($item.Key)"
        }
    }

    Write-Host ""
    Write-Host "PASS: комплект проверен" -ForegroundColor Green
    Write-Host "Выпуск: $releaseId"
    Write-Host "Проверено файлов: $checked"
    Write-Host "Статус: готов к прошивке, аппаратная валидация ожидается"
    exit 0
}
catch {
    Write-Host ""
    Write-Host "FAIL: комплект не прошел проверку" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
