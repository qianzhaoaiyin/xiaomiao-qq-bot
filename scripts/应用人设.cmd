@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
title 应用人设
echo ============================================================
echo    把 persona\人设.txt 应用到机器人
echo ------------------------------------------------------------
echo    用法：
echo      1. 用记事本改 persona\人设.txt
echo      2. 双击本脚本
echo    不用重启 kirara，改完立刻生效。
echo ============================================================
echo.
"%PY%" "%ROOT%\bot\apply_persona.py"
echo.
pause
