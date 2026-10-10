# -*- coding: utf-8 -*-
"""守护进程：掉线自动拉起 + 状态自检 + 出事通知主人。

    python bot/watchdog.py            # 常驻守护（每 WATCHDOG_INTERVAL 秒巡检一次）
    python bot/watchdog.py --once     # 只打印一次状态报告就退出

巡检四项：
  1. 表情包图库（GALLERY_PORT）
  2. kirara 主程序（8080）
  3. NapCat 协议端（NAPCAT_WEBUI_PORT）
  4. QQ 登录态（NapCat 本地 HTTP API 3002 的 get_login_info）

设计上的两个克制：
  * 存在 logs/.pause 标记时**只报告不重启**——scripts\停止.cmd 会创建它，
    否则你刚手动停掉，守护又给你拉起来，两个人打架。
  * 通知主人走 NapCat 的 HTTP API 发私聊消息，只在状态**发生变化**时发一次，
    不刷屏。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

import paths

LOG_DIR = paths.ROOT / "logs"
LOG_FILE = LOG_DIR / "watchdog.log"
PAUSE_FILE = LOG_DIR / ".pause"
STATE_FILE = LOG_DIR / "watchdog-state.json"
NAPCAT_HTTP = "http://127.0.0.1:3002"
MAX_LOG_BYTES = 2 * 1024 * 1024

# ---- 熔断参数（防风控，别调大）----
# 腾讯会检测机器人。参考 ai-companion-kit 教程第十三章：对方通道已经出问题的时候
# 还每 15 秒重试一次，"失败次数 ≈ 成功次数"，在腾讯眼里就是标准机器人。
# 症状不是封号而是限速：服务端开始不回包（code=-1 gotResponse=false）。
# 所以连续拉起失败就停手，别骚扰服务器。
FAIL_STRIKES = 3# 连续几次拉起不到就算失败
COOLDOWN_SEC = 600           # 熔断后冷静多久（秒）
BOOT_WAIT_SEC = 45           # 拉起后等多久算"起来了"

# ---- 藏窗口 ----
# NapCat 拉起的 QQ.exe 是控制台子系统程序，它会**自己** AllocConsole 开一个
# ConsoleWindowClass 窗口（标题是 QQ.exe 的完整路径）。
# 我们给 NapCat 启动器传的 DETACHED_PROCESS 只对它自己生效，管不到 QQ.exe。
# 开机自启时这个窗口会直接怼到桌面上，只能事后藏。
HIDE_QQ_WINDOW = (paths.env("HIDE_QQ_WINDOW") or "1") != "0"
_CONSOLE_CLASSES = ("ConsoleWindowClass", "PseudoConsoleWindow", "CASCADIA_HOSTING_WIN")
_QQ_PROCS = ("qq.exe", "napcatwinbootmain.exe")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "XiaomiaoQQBot"

_breaker = {}


def log(msg):
    line = "%s %s" % (datetime.now().strftime("%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
            os.replace(str(LOG_FILE), str(LOG_FILE) + ".1")
        with open(str(LOG_FILE), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def port_open(port, host="127.0.0.1"):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, int(port))) == 0


def napcat_call(action, **params):
    body = json.dumps(params).encode()
    req = urllib.request.Request(NAPCAT_HTTP + "/" + action, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def qq_login():
    """返回 (是否在线, 描述)。"""
    if not port_open(3002):
        return False, "NapCat HTTP API(3002) 未响应"
    try:
        d = napcat_call("get_login_info")
        data = d.get("data") or {}
        if data.get("user_id"):
            return True, "%s (%s)" % (data["user_id"], data.get("nickname", ""))
        return False, "未登录"
    except Exception as e:
        return False, "查询失败 %s" % str(e)[:60]


def start_gallery():
    log("  拉起 图库服务 ...")
    subprocess.Popen([paths.find_python(), str(paths.BOT_DIR / "gallery_server.py")],
                     cwd=str(paths.ROOT), creationflags=_flags(),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_kirara():
    log("  拉起 kirara 主程序 ...")
    subprocess.Popen([paths.find_python(), "-m", "kirara_ai"],
                     cwd=str(paths.KIRARA_DIR), creationflags=_flags(),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_napcat():
    try:
        exe = paths.napcat_launcher()
    except FileNotFoundError as e:
        log("  [!] %s" % e)
        return
    log("  拉起 NapCat ...")
    subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=_flags())


def _flags():
    """子进程不分配控制台、脱离本进程组。

    注意用 CREATE_NO_WINDOW 而不是"最小化"：最小化的窗口仍在任务栏里，不算无痕。
    """
    if os.name != "nt":
        return 0
    return 0x08000000 | 0x00000008 | 0x00000200  # NO_WINDOW | DETACHED | NEW_PROCESS_GROUP


# ------------------------------------------------------------------ 熔断
def breaker_allow(name):
    st = _breaker.get(name)
    return not st or time.time() >= st["open_until"]


def breaker_fail(name):
    st = _breaker.setdefault(name, {"strikes": 0, "open_until": 0})
    st["strikes"] += 1
    if st["strikes"] >= FAIL_STRIKES:
        st["open_until"] = time.time() + COOLDOWN_SEC
        st["strikes"] = 0
        log("★ 熔断 %s：连续 %d 次拉起都没成功，暂停重试 %d 秒"
            % (name, FAIL_STRIKES, COOLDOWN_SEC))
        log("  盲目重试会被腾讯当成机器人。被限速时先停一天别聊，再看 --once 的输出。")
        return False
    return True


def breaker_ok(name):
    if name in _breaker:
        _breaker[name]["strikes"] = 0


# ------------------------------------------------------------------ 藏窗口
def _napcat_pids():
    """属于本实例的 NapCat / QQ 进程 PID 集合。"""
    try:
        import psutil
    except ImportError:
        return set()
    pids = set()
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (p.info["name"] or "").lower()
            cmd = " ".join(p.info["cmdline"] or [])
        except Exception:
            continue
        if name in _QQ_PROCS and str(paths.NAPCAT_DIR).lower() in cmd.lower():
            pids.add(p.pid)
    return pids


def _each_window(pids):
    """枚举这些进程的顶层窗口，返回 (hwnd, 窗口类, 是否可见, pid)。"""
    import ctypes
    from ctypes import wintypes
    if os.name != "nt":
        return []
    try:
        u = ctypes.windll.user32
    except Exception:
        return []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    out = []

    def cb(h, _):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids:
            cls = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(h, cls, 256)
            out.append((h, cls.value, bool(u.IsWindowVisible(h)), pid.value))
        return True

    u.EnumWindows(proto(cb), 0)
    return out


def hide_napcat_windows(verbose=False):
    """把 QQ.exe 自己开的控制台窗口藏掉，返回藏了几个。

    为什么不用"最小化"：最小化的窗口还在任务栏里，用户一眼就看到有东西在跑。
    要"完全静默"就得让窗口从来没被创建过，或者创建后立刻藏掉。
    """
    if os.name != "nt" or not HIDE_QQ_WINDOW:
        return 0
    import ctypes
    pids = _napcat_pids()
    if not pids:
        return 0
    hidden = 0
    for hwnd, cls, vis, pid in _each_window(pids):
        if vis and cls in _CONSOLE_CLASSES:
            ctypes.windll.user32.ShowWindow(hwnd, 0)   # SW_HIDE
            hidden += 1
            if verbose:
                log("  已藏起 %s 的控制台窗口（PID %d）" % (cls, pid))
    return hidden


def show_qq_windows():
    """把窗口显示出来 —— 掉登录需要人扫码时用。"""
    import ctypes
    pids = _napcat_pids()
    if not pids:
        print("没找到 NapCat/QQ 进程")
        return
    n = 0
    for hwnd, cls, _vis, _pid in _each_window(pids):
        if cls in _CONSOLE_CLASSES:
            ctypes.windll.user32.ShowWindow(hwnd, 5)   # SW_SHOW
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            n += 1
    print("已显示 %d 个窗口，扫码吧。扫完关掉，守护会重新藏起来。" % n)


# ------------------------------------------------------------------ 开机自启
def autostart_installed():
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return bool(winreg.QueryValueEx(k, RUN_NAME)[0])
    except FileNotFoundError:
        return False
    except Exception:
        return False


def install_autostart():
    import winreg
    cmd = paths.autostart_command()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, cmd)
    print("已开启开机静默自启：")
    print("  位置：HKEY_CURRENT_USER\\%s\\%s" % (RUN_KEY, RUN_NAME))
    print("  命令：%s" % cmd)
    print()
    print("下次登录 Windows 会自动静默启动（不弹任何窗口）。")
    print("注意：注册表 Run 项是**登录后**才跑，不是开机就跑。")


def uninstall_autostart():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as k:
            winreg.DeleteValue(k, RUN_NAME)
        print("已关闭开机自启。")
    except FileNotFoundError:
        print("本来就没有开机自启。")


def notify(text):
    """通过 NapCat 给主人发一条私聊。失败只记日志，不抛异常。"""
    owner = (paths.env("OWNER_QQ") or "").strip()
    if not owner:
        log("  [通知跳过] .env 里没填 OWNER_QQ：" + text)
        return
    try:
        napcat_call("send_private_msg", user_id=int(owner),
                    message=[{"type": "text", "data": {"text": text}}])
        log("  [已通知主人] " + text)
    except Exception as e:
        log("  [通知失败] %s | %s" % (str(e)[:80], text))


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def is_paused():
    """logs/.guard 内容为 paused 时只报告不重启。

    用文件内容而不是"文件是否存在"来判断，这样 一键启动/停止 只需要覆写它，
    不必删文件（避免脚本里出现删除操作）。
    """
    try:
        return PAUSE_FILE.read_text(encoding="utf-8").strip().startswith("paused")
    except Exception:
        return False


def set_guard(state):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PAUSE_FILE.write_text("%s\n%s\n" % (state, datetime.now().strftime("%F %T")),
                          encoding="utf-8")
    print("守护已%s（%s）" % ("暂停" if state == "paused" else "恢复", PAUSE_FILE))


def probe():
    """返回 {项目: (是否ok, 描述)}"""
    gp = paths.gallery_port()
    np = int(paths.env("NAPCAT_WEBUI_PORT") or 6100)
    out = {}
    out["图库"] = (port_open(gp), "端口 %d" % gp)
    out["kirara"] = (port_open(paths.KIRARA_PORT), "端口 %d" % paths.KIRARA_PORT)
    out["NapCat"] = (port_open(np), "端口 %d" % np)
    ok, detail = qq_login()
    out["QQ登录"] = (ok, detail)
    return out


def report():
    st = probe()
    total = sum(1 for v in st.values() if v[0])
    print("=" * 58)
    print("  小喵机器人状态  %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 58)
    for k, (ok, d) in st.items():
        print("  [%s] %-8s %s" % ("正常" if ok else "异常", k, d))
    try:
        g = json.loads(urllib.request.urlopen(paths.gallery_url() + "/list", timeout=6).read().decode())
        s = json.loads(urllib.request.urlopen(paths.gallery_url() + "/stolen", timeout=6).read().decode())
        print("  [信息] 图库共 %d 张（自动收录 %d 张，已打标 %d 张）"
              % (sum(g.values()), s.get("已收录", 0), s.get("已打标", 0)))
    except Exception as e:
        print("  [信息] 图库统计不可用：%s" % str(e)[:60])
    print("  [信息] 守护状态：%s" % ("已暂停（不会自动重启）" if is_paused() else "运行中"))
    print("=" * 58)
    return total == len(st)


def restart_component(name, port, spawn, wait):
    """掉线了就把这一个拉起来。拉不起来就记一次熔断。

    分成"一个组件一个组件"是有意的：某一项失败不该把其它项也拖下水，
    更不该形成无限重试风暴。
    """
    if port_open(port):
        breaker_ok(name)
        return True
    if not breaker_allow(name):
        log("  %s 还在熔断期，本轮不重试" % name)
        return False
    log("  %s 掉线（端口 %d），拉起 ..." % (name, port))
    try:
        spawn()
    except Exception as e:
        log("  %s 拉起时报错：%s" % (name, str(e)[:100]))
        breaker_fail(name)
        return False
    deadline = time.time() + BOOT_WAIT_SEC
    while time.time() < deadline:
        time.sleep(5)
        if port_open(port):
            log("  %s 已恢复" % name)
            breaker_ok(name)
            return True
    log("  %s 拉起后 %d 秒仍未监听端口 %d" % (name, BOOT_WAIT_SEC, port))
    breaker_fail(name)
    return False


def tick():
    st = probe()
    prev = load_state()
    paused = is_paused()
    changed = []

    for name, (ok, detail) in st.items():
        was = prev.get(name)
        if was is not None and was != ok:
            changed.append((name, ok, detail))
        prev[name] = ok

    if not ok_all(st) and not paused:
        gp = paths.gallery_port()
        np_ = int(paths.env("NAPCAT_WEBUI_PORT") or 6100)
        # 顺序有讲究：协议端先起，主程序再起，图库最后（互不依赖但先重后轻）
        restart_component("NapCat", np_, start_napcat, 15)
        restart_component("kirara", paths.KIRARA_PORT, start_kirara, 12)
        restart_component("图库", gp, start_gallery, 3)
        # QQ.exe 起来后会自己开一个控制台窗口，连藏几次（它可能晚几秒才弹）
        for _ in range(6):
            hide_napcat_windows(verbose=True)
            time.sleep(2)
        st = probe()

    hide_napcat_windows(verbose=True)

    for name, ok, detail in changed:
        log("%s -> %s（%s）" % (name, "恢复" if ok else "异常", detail))
        if name in ("QQ登录", "kirara") and not ok:
            notify("【小喵】%s 异常：%s" % (name, detail))
        elif name == "QQ登录" and ok:
            notify("【小喵】QQ 已重新上线：%s" % detail)

    save_state(prev)
    return st


def ok_all(st):
    return all(v[0] for v in st.values())


def main():
    if "--pause" in sys.argv:
        return set_guard("paused")
    if "--resume" in sys.argv:
        return set_guard("running")
    if "--install-autostart" in sys.argv:
        return install_autostart()
    if "--uninstall-autostart" in sys.argv:
        return uninstall_autostart()
    if "--show-qq" in sys.argv:
        return show_qq_windows()
    if "--once" in sys.argv:
        sys.exit(0 if report() else 1)
    interval = int(paths.env("WATCHDOG_INTERVAL") or 60)
    paths.ensure_dirs()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log("守护启动，每 %d 秒巡检一次（暂停标记：%s）" % (interval, PAUSE_FILE))
    log("熔断：连续 %d 次拉不起就暂停 %d 秒；藏窗口：%s"
        % (FAIL_STRIKES, COOLDOWN_SEC, "开" if HIDE_QQ_WINDOW else "关"))
    log("开机自启：%s" % ("已开启" if autostart_installed() else "未开启"))
    notify("【小喵】守护进程已启动，我会自己照顾自己了")
    while True:
        try:
            tick()
        except Exception as e:
            log("巡检异常：%s: %s" % (type(e).__name__, str(e)[:120]))
        time.sleep(interval)


if __name__ == "__main__":
    main()
