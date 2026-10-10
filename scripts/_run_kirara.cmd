@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
title kirara 主程序
cd /d "%ROOT%\kirara"
"%PY%" -m kirara_ai
echo.
echo kirara 已退出
pause
