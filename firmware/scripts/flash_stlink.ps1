param(
  [Parameter(Mandatory=$true)][string]$Image,
  [string]$Cli = "STM32_Programmer_CLI.exe"
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Image)) { throw "Firmware image not found: $Image" }
& $Cli -c port=SWD mode=UR reset=HWrst -e all -w $Image -v -rst
if ($LASTEXITCODE -ne 0) { throw "STM32CubeProgrammer failed with $LASTEXITCODE" }
Write-Host "Flash and verification PASS"
