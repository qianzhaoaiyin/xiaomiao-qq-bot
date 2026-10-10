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
    return 0x00000008 if os.name == "nt" else 0   # DETACHED_PROCESS


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
        if not st["图库"][0]:
            start_gallery()
            time.sleep(3)
        if not st["kirara"][0]:
            start_kirara()
            time.sleep(12)
        if not st["NapCat"][0]:
            start_napcat()
            time.sleep(15)
        st = probe()

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
    if "--once" in sys.argv:
        sys.exit(0 if report() else 1)
    interval = int(paths.env("WATCHDOG_INTERVAL") or 60)
    paths.ensure_dirs()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log("守护启动，每 %d 秒巡检一次（暂停标记：%s）" % (interval, PAUSE_FILE))
    notify("【小喵】守护进程已启动，我会自己照顾自己了")
    while True:
        try:
            tick()
        except Exception as e:
            log("巡检异常：%s: %s" % (type(e).__name__, str(e)[:120]))
        time.sleep(interval)


if __name__ == "__main__":
    main()
