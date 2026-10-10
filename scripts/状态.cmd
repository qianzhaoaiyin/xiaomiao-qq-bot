@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
title Ð¡ß÷ QQ »úÆ÷ÈË - ×´Ì¬
"%PY%" "%ROOT%\bot\watchdog.py" --once
echo.
pause
