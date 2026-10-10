@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
title 小喵 QQ 机器人 - 安装
echo ============================================================
echo    小喵 QQ 机器人  一键安装
echo ------------------------------------------------------------
echo    会下载 kirara-ai（约 210MB）和 NapCat（约 118MB），
echo    然后装插件、写配置。中途别关窗口。
echo ============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\install.ps1"
echo.
pause
