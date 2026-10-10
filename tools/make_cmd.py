# -*- coding: utf-8 -*-
r"""生成 scripts\ 下的所有 .cmd（GBK + CRLF）。

为什么要这个生成器：**Windows 批处理必须是 GBK(代码页936) + CRLF**。
用普通编辑器或脚本写出来默认是 UTF-8 无 BOM + LF，双击运行会报「命令语法不正确」——
UTF-8 的中文字节被 cmd 按 GBK 解析，某些字节会撞成 | % 之类的控制字符，
再加上 LF 换行会让 call/goto/for 解析错位。

所以：要改 .cmd，请改这个文件里的文本，然后跑一次
    python tools\make_cmd.py
不要直接用编辑器改 scripts\*.cmd（会被存成 UTF-8 而失效）。
另外不要在 GBK 的 .cmd 里写 chcp 65001，会和文件编码打架。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "scripts")

HEADER = '@echo off\nsetlocal\ncd /d "%~dp0.."\nset "ROOT=%CD%"\n'

FIND_PY = r'''set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
'''

READ_ENV = r'''set "GALLERY_PORT=3100"
set "NAPCAT_PORT=6100"
if exist "%ROOT%\.env" for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT%\.env") do (
    if /i "%%a"=="GALLERY_PORT" set "GALLERY_PORT=%%b"
    if /i "%%a"=="NAPCAT_WEBUI_PORT" set "NAPCAT_PORT=%%b"
)
'''

SCRIPTS = {}

SCRIPTS["安装.cmd"] = HEADER + '''title 小喵 QQ 机器人 - 安装
echo ============================================================
echo    小喵 QQ 机器人  一键安装
echo ------------------------------------------------------------
echo    会下载 kirara-ai（约 210MB）和 NapCat（约 118MB），
echo    然后装插件、写配置。中途别关窗口。
echo ============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\\scripts\\install.ps1"
echo.
pause
'''

SCRIPTS["一键启动.cmd"] = HEADER + FIND_PY + READ_ENV + r'''title 小喵 QQ 机器人 - 一键启动
echo ============================================================
echo    小喵 QQ 机器人  一键启动
echo ------------------------------------------------------------
echo    管理后台   http://127.0.0.1:8080
echo    NapCat     http://127.0.0.1:%NAPCAT_PORT%
echo    表情包图库 http://127.0.0.1:%GALLERY_PORT%/list
echo ============================================================
echo.
"%PY%" "%ROOT%\bot\watchdog.py" --resume
echo.

netstat -na | findstr "LISTENING" | findstr ":%GALLERY_PORT% " >nul
if errorlevel 1 (
    echo [1/3] 启动 表情包图库 ...
    start "图库" /min "%PY%" "%ROOT%\bot\gallery_server.py"
    timeout /t 2 /nobreak >nul
) else (
    echo [1/3] 图库已在运行，跳过（端口 %GALLERY_PORT%）
)

netstat -na | findstr "LISTENING" | findstr ":8080 " >nul
if errorlevel 1 (
    echo [2/3] 启动 kirara 主程序 ...
    start "kirara" cmd /c "%ROOT%\scripts\_run_kirara.cmd"
    echo       等 15 秒让它把服务拉起来 ...
    timeout /t 15 /nobreak >nul
) else (
    echo [2/3] kirara 已在运行，跳过（端口 8080）
)

netstat -na | findstr "LISTENING" | findstr ":%NAPCAT_PORT% " >nul
if errorlevel 1 (
    echo [3/3] 启动 NapCat 协议端 ...
    set "NAP="
    for /r "%ROOT%\napcat" %%F in (NapCatWinBootMain.exe NapCatBoot.exe) do if exist "%%F" set "NAP=%%F"
    if defined NAP (
        for %%I in ("!NAP!") do start "NapCat" /D "%%~dpI" "%%~dpI%%~nxI"
        echo       等 12 秒 ...
        timeout /t 12 /nobreak >nul
    ) else (
        echo       [!] napcat 目录里找不到启动器，请先跑 scripts\安装.cmd
    )
) else (
    echo [3/3] NapCat 已在运行，跳过（端口 %NAPCAT_PORT%）
)

echo.
echo ============================================================
echo    启动完成。NapCat 还要 10~30 秒把 QQ 登上去。
echo ------------------------------------------------------------
echo    如果 QQ 掉登录了，去 NapCat 窗口或
echo    http://127.0.0.1:%NAPCAT_PORT% 扫码。
echo    主程序窗口里出现 OneBot ... Connected 就说明接通了。
echo.
echo    之后在 QQ 里给机器人发消息即可。
echo ============================================================
echo.
pause
'''.replace("setlocal", "setlocal enabledelayedexpansion")

SCRIPTS["_run_kirara.cmd"] = HEADER + FIND_PY + '''title kirara 主程序
cd /d "%ROOT%\\kirara"
"%PY%" -m kirara_ai
echo.
echo kirara 已退出
pause
'''

SCRIPTS["启动图库.cmd"] = HEADER + FIND_PY + READ_ENV + '''title 表情包图库
netstat -na | findstr "LISTENING" | findstr ":%GALLERY_PORT% " >nul
if not errorlevel 1 (
    echo 图库已在运行（端口 %GALLERY_PORT%），不重复启动
    pause
    exit /b
)
echo 启动表情包图库 ...
start "图库" /min "%PY%" "%ROOT%\\bot\\gallery_server.py"
timeout /t 2 /nobreak >nul
echo 已启动：http://127.0.0.1:%GALLERY_PORT%
echo 图库目录：%ROOT%\\表情包   （往里放图即生效，也会在聊天中自动收录）
echo.
pause
'''

SCRIPTS["停止.cmd"] = HEADER + FIND_PY + READ_ENV + r'''title 小喵 QQ 机器人 - 停止
echo ============================================================
echo    小喵 QQ 机器人  停止
echo ============================================================
echo.
"%PY%" "%ROOT%\bot\watchdog.py" --pause
call :kill %NAPCAT_PORT% NapCat协议端
call :kill 8080 kirara主程序
call :kill %GALLERY_PORT% 表情包图库
echo.
echo    已停止。只结束监听这几个端口的进程及其子进程。
echo    守护也已暂停，不会把它们再拉起来。
echo ============================================================
echo.
pause
exit /b

:kill
set "_P="
for /f "tokens=5" %%a in ('netstat -nao ^| findstr "LISTENING" ^| findstr ":%~1 "') do set "_P=%%a"
if not defined _P goto kill_none
echo   正在结束 %~2 （端口 %~1, PID %_P%）...
taskkill /PID %_P% /T /F >nul 2>&1
echo   已结束
exit /b

:kill_none
echo   %~2 未在运行（端口 %~1）
exit /b
'''

SCRIPTS["守护.cmd"] = HEADER + FIND_PY + '''title 小喵 QQ 机器人 - 守护
echo ============================================================
echo    守护进程：掉线自动拉起，状态变化时给你发 QQ 私聊
echo ------------------------------------------------------------
echo    巡检间隔由 .env 的 WATCHDOG_INTERVAL 控制（默认 60 秒）
echo    按 Ctrl+C 或关窗口即可停止守护（不会停机器人）
echo    想彻底停机器人请用 scripts\\停止.cmd
echo ============================================================
echo.
"%PY%" "%ROOT%\\bot\\watchdog.py"
pause
'''

SCRIPTS["状态.cmd"] = HEADER + FIND_PY + '''title 小喵 QQ 机器人 - 状态
"%PY%" "%ROOT%\\bot\\watchdog.py" --once
echo.
pause
'''

SCRIPTS["应用人设.cmd"] = HEADER + FIND_PY + '''title 应用人设
echo ============================================================
echo    把 persona\\人设.txt 应用到机器人
echo ------------------------------------------------------------
echo    用法：
echo      1. 用记事本改 persona\\人设.txt
echo      2. 双击本脚本
echo    不用重启 kirara，改完立刻生效。
echo ============================================================
echo.
"%PY%" "%ROOT%\\bot\\apply_persona.py"
echo.
pause
'''

SCRIPTS["配置.cmd"] = HEADER + FIND_PY + '''title 写入配置与工作流
echo ============================================================
echo    把 config\\ 下的配置和工作流灌进 kirara / NapCat
echo ------------------------------------------------------------
echo    kirara 没在跑 -^> 只写文件（--offline）
echo    kirara 在跑   -^> 写完文件再写工作流并自测
echo ============================================================
echo.
"%PY%" "%ROOT%\\bot\\provision.py"
echo.
pause
'''

SCRIPTS["自测.cmd"] = HEADER + FIND_PY + '''title 自测
echo ============================================================
echo    不依赖 QQ 的端到端自测（走内置 http_legacy 通道）
echo ============================================================
echo.
"%PY%" "%ROOT%\\bot\\selftest.py"
echo.
pause
'''


def build(name, text):
    return text.replace("\r\n", "\n").replace("\n", "\r\n").encode("gbk", "replace")


def check():
    r"""CI 用：确认 scripts\*.cmd 与生成器一致、编码正确、没被手改坏。"""
    bad = 0
    for name, text in SCRIPTS.items():
        p = os.path.join(OUT, name)
        want = build(name, text)
        if not os.path.isfile(p):
            print("  [缺失] %s —— 请运行 python tools\\make_cmd.py" % name)
            bad += 1
            continue
        raw = open(p, "rb").read()
        try:
            raw.decode("gbk")
        except Exception as e:
            print("  [编码错] %s 不是合法 GBK：%s" % (name, e))
            bad += 1
            continue
        if b"\r\n" not in raw:
            print("  [换行错] %s 不是 CRLF" % name)
            bad += 1
        if b"/dev/null" in raw:
            print("  [污染] %s 含 /dev/null（MSYS 把 >nul 改写过）" % name)
            bad += 1
        if raw != want:
            print("  [不同步] %s 与 make_cmd.py 里的定义不一致，请重新生成" % name)
            bad += 1
        else:
            print("  [ok] %s" % name)
    print("\n检查完成：%d 个问题" % bad)
    return 1 if bad else 0


def main():
    if "--check" in sys.argv:
        return check()
    os.makedirs(OUT, exist_ok=True)
    for name, text in SCRIPTS.items():
        p = os.path.join(OUT, name)
        data = build(name, text)
        with open(p, "wb") as f:
            f.write(data)
        # 自检：必须能用 GBK 解回来，且必须是 CRLF
        raw = open(p, "rb").read()
        raw.decode("gbk")
        assert b"\r\n" in raw, name + " 缺 CRLF"
        assert b"/dev/null" not in raw, name + " 出现了 /dev/null（MSYS 污染）"
        print("  [生成] %-16s %5d bytes  GBK+CRLF ok" % (name, len(raw)))
    print("\n共 %d 个脚本，位于 %s" % (len(SCRIPTS), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
