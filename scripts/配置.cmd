@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
title 写入配置与工作流
echo ============================================================
echo    把 config\ 下的配置和工作流灌进 kirara / NapCat
echo ------------------------------------------------------------
echo    kirara 没在跑 -^> 只写文件（--offline）
echo    kirara 在跑   -^> 写完文件再写工作流并自测
echo ============================================================
echo.
"%PY%" "%ROOT%\bot\provision.py"
echo.
pause
