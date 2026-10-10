@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
title 自测
echo ============================================================
echo    不依赖 QQ 的端到端自测（走内置 http_legacy 通道）
echo ============================================================
echo.
"%PY%" "%ROOT%\bot\selftest.py"
echo.
pause
