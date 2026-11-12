@echo off
setlocal
chcp 65001 >nul
title Проверка комплекта EVT-PRE-20
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_package.ps1" -PackageRoot "%~dp0.."
set "result=%ERRORLEVEL%"
echo.
if "%result%"=="0" (
  echo Проверка завершена успешно. Можно переходить к инструкции по прошивке.
) else (
  echo Проверка завершилась ошибкой. Не прошивайте станцию. Передайте текст ошибки инженеру.
)
echo.
pause
exit /b %result%
