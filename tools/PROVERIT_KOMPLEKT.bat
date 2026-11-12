@echo off
setlocal
title EVT-PRE-20 package verification
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_package.ps1" -PackageRoot "%~dp0.."
set "result=%ERRORLEVEL%"
echo.
if "%result%"=="0" (
  echo PASS: verification completed. Follow the flashing instruction.
) else (
  echo FAIL: do not flash the station. Send the error text to the engineer.
)
echo.
pause
exit /b %result%
