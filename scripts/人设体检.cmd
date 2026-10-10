@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
title 人设体检
echo ============================================================
echo    检查 persona\ 下的两份文件有没有常见毛病
echo ------------------------------------------------------------
echo    改完人设先跑这个，再跑 应用人设.cmd
echo ============================================================
echo.
"%PY%" "%ROOT%\tools\lint_persona.py"
echo.
pause
