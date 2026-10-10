@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
title 小喵 QQ 机器人 - 守护
echo ============================================================
echo    守护进程：掉线自动拉起，状态变化时给你发 QQ 私聊
echo ------------------------------------------------------------
echo    巡检间隔由 .env 的 WATCHDOG_INTERVAL 控制（默认 60 秒）
echo    按 Ctrl+C 或关窗口即可停止守护（不会停机器人）
echo    想彻底停机器人请用 scripts\停止.cmd
echo ============================================================
echo.
"%PY%" "%ROOT%\bot\watchdog.py"
pause
