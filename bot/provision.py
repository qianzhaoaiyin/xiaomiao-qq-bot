# -*- coding: utf-8 -*-
"""一键把仓库里的配置灌进 kirara / NapCat。

    python bot/provision.py --offline   # 只写文件，不需要 kirara 在跑（安装时用）
    python bot/provision.py --online    # 通过 API 写工作流并自测（kirara 起来后用）
    python bot/provision.py             # 先 offline 再 online

设计原则：**幂等**。反复运行结果一致，不会重复追加、不会覆盖你自己的改动之外的东西。
"""
import json
import re
import secrets
import shutil
import sys
import time

import paths
import patch_humanize_send
import patch_person_memory
import patch_sticker_source

DEFAULT_LLM = "deepseek-flash"


def _write(p, text):
    open(str(p), "w", encoding="utf-8", newline="\n").write(text)


def _backup(p):
    p = str(p)
    import os
    if os.path.isfile(p):
        b = p + ".bak-" + time.strftime("%Y%m%d%H%M%S")
        shutil.copy2(p, b)
        return b
    return None


# ---------------------------------------------------------------- offline
def ensure_env():
    if paths.ENV_FILE.exists():
        return paths.load_env()
    if (paths.ROOT / ".env.example").exists():
        shutil.copy2(str(paths.ROOT / ".env.example"), str(paths.ENV_FILE))
    print("  [!] 已生成 .env，请填入 DEEPSEEK_API_KEY 后重新运行本脚本")
    sys.exit(2)


def onebot_token(env):
    """反向 WS 的握手口令。留空就现生成一个随机的，避免用户忘了填。"""
    tok = (env.get("ONEBOT_TOKEN") or "").strip()
    if tok and "在这里填" in tok:
        tok = ""
    if not tok:
        tok = secrets.token_urlsafe(18)
        print("  [生成] .env 里没写 ONEBOT_TOKEN，已自动生成一个随机口令")
    return tok


def write_kirara_config(env):
    tpl = paths.CONFIG_DIR / "kirara.config.yaml"
    dst = paths.kirara_data_dir() / "config.yaml"
    if not tpl.exists():
        print("  [跳过] 找不到模板 %s" % tpl)
        return
    key = env.get("DEEPSEEK_API_KEY", "")
    if not key or "在这里填" in key:
        print("  [!] .env 里的 DEEPSEEK_API_KEY 还没填，先跳过主配置")
        return
    text = tpl.read_text(encoding="utf-8").replace("${DEEPSEEK_API_KEY}", key)
    text = text.replace("${ONEBOT_TOKEN}", onebot_token(env))
    # 原始模板里默认模型是个不存在的 gemini-1.5-flash，纠正成我们真配了的模型
    text = re.sub(r"(llm_model:\s*)\S+", r"\g<1>" + DEFAULT_LLM, text)
    dst.parent.mkdir(parents=True, exist_ok=True)
    b = _backup(dst)
    _write(dst, text)
    print("  [写入] kirara/data/config.yaml%s" % ("（原文件备份 %s）" % b.split("\\")[-1] if b else ""))
    print("         模型：deepseek-flash / deepseek-v4-pro / deepseek-v4-flash-vision-exp")


def write_rules(kirara_running):
    """按 .env 里有没有 OWNER_QQ 选择规则集。

    填了 OWNER_QQ -> config/rules.owner.yaml（严格模式：只回主人、群里被@才回、
                     陌生人私聊静默）
    没填          -> config/rules.yaml（宽松模式：谁都能聊、群里每条都回）
    """
    env = paths.load_env()
    owner = (env.get("OWNER_QQ") or "").strip()
    src = paths.CONFIG_DIR / ("rules.owner.yaml" if owner else "rules.yaml")
    dst = paths.kirara_data_dir() / "dispatch_rules" / "rules.yaml"
    if not src.exists():
        print("  [跳过] 找不到 %s" % src)
        return
    if kirara_running:
        print("  [!] kirara 正在运行，跳过 rules.yaml —— 它退出时会用内存里的旧规则覆盖回去。")
        print("      要改规则请先跑 scripts\\停止.cmd，再执行 provision.py --offline")
        return
    text = src.read_text(encoding="utf-8").replace("${OWNER_QQ}", owner)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _backup(dst)
    _write(dst, text)
    if owner:
        print("  [写入] rules.yaml（严格模式）：只回主人 %s，群里被@/命令才回，陌生人静默" % owner)
    else:
        print("  [写入] rules.yaml（宽松模式）：任何人都能聊、群里每条都回")
        print("         建议在 .env 里填 OWNER_QQ 启用严格模式，省钱也防骚扰")


def write_napcat_config(env):
    try:
        cfg_dir = paths.napcat_config_dir()
    except FileNotFoundError as e:
        print("  [跳过] %s" % e)
        return
    # 1) OneBot 反向 WS
    src = paths.CONFIG_DIR / "napcat.onebot11.json"
    if src.exists():
        # 模板里写的是 ${ONEBOT_TOKEN} 占位符，抄过去之前先替换掉
        raw = src.read_text(encoding="utf-8")
        raw = raw.replace("${ONEBOT_TOKEN}", onebot_token(env))
        for name in ("onebot11.json",):
            dst = cfg_dir / name
            _backup(dst)
            dst.write_text(raw, encoding="utf-8")
            print("  [写入] NapCat %s（反向 WS -> kirara:8080，本地 HTTP 3002）" % name)
        bot_qq = (env.get("BOT_QQ") or "").strip()
        if bot_qq:
            dst = cfg_dir / ("onebot11_%s.json" % bot_qq)
            if not dst.exists():
                dst.write_text(raw, encoding="utf-8")
                print("  [写入] NapCat onebot11_%s.json" % bot_qq)
    # 2) WebUI 端口钉死 + 自动登录账号
    webui = cfg_dir / "webui.json"
    if webui.exists():
        try:
            d = json.loads(webui.read_text(encoding="utf-8"))
        except Exception as e:
            print("  [跳过] webui.json 解析失败：%s" % e)
            return
        port = int(env.get("NAPCAT_WEBUI_PORT") or 6100)
        changed = []
        if d.get("port") != port:
            d["port"] = port
            changed.append("端口=%d" % port)
        bot_qq = (env.get("BOT_QQ") or "").strip()
        if bot_qq and d.get("autoLoginAccount") != bot_qq:
            d["autoLoginAccount"] = bot_qq
            changed.append("自动登录=%s" % bot_qq)
        if changed:
            _backup(webui)
            webui.write_text(json.dumps(d, ensure_ascii=False, indent=4), encoding="utf-8")
            print("  [改] NapCat webui.json：%s" % "，".join(changed))
            print("       （端口钉死很重要：多开时 NapCat 会自动递增端口，"
                  "按端口判断的启停脚本会认错甚至误杀另一套）")
        else:
            print("  [跳过] NapCat webui.json 已是目标值")
    else:
        print("  [提示] 还没生成 webui.json，先启动一次 NapCat 再跑 provision 即可钉端口")


def offline():
    print("=" * 60)
    print("  [1/2] 写配置文件（不需要 kirara 在跑）")
    print("=" * 60)
    env = ensure_env()
    paths.ensure_dirs()
    running = _port_open(paths.KIRARA_PORT)
    write_kirara_config(env)
    write_rules(running)
    write_napcat_config(env)
    print("  [补丁] 表情包图源 -> 本地图库")
    try:
        patch_sticker_source.patch()
    except SystemExit as e:
        print("  [!] %s" % e)
    except FileNotFoundError as e:
        print("  [跳过] %s" % e)

    print("  [补丁] 拟人化发送（分条之间有停顿）")
    try:
        patch_humanize_send.patch()
    except SystemExit as e:
        print("  [!] %s" % e)
    except FileNotFoundError as e:
        print("  [跳过] %s" % e)

    # 跨场合记忆要改工作流里的记忆块，kirara 在跑的时候它退出时会用内存里的
    # 旧值覆盖回去，所以必须等它停了再打
    if running:
        print("  [跳过] 跨场合记忆补丁（kirara 在跑，请先 scripts\\停止.cmd 再执行一次 provision）")
    else:
        print("  [补丁] 跨场合记忆（按人存）")
        try:
            patch_person_memory.patch()
        except SystemExit as e:
            print("  [!] %s" % e)
        except FileNotFoundError as e:
            print("  [跳过] %s" % e)


# ---------------------------------------------------------------- online
def _port_open(port, host="127.0.0.1"):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


def online():
    from kirara_api import Kirara, KiraraError
    print()
    print("=" * 60)
    print("  [2/2] 写入工作流并自测（需要 kirara 在跑）")
    print("=" * 60)
    if not _port_open(paths.KIRARA_PORT):
        print("  [!] kirara 没在 %d 端口上，先跑 scripts\\一键启动.cmd 再执行 --online" % paths.KIRARA_PORT)
        return
    k = Kirara()
    try:
        k.wait_boot(timeout=120)
    except KiraraError as e:
        print("  [!] %s" % e)
        return

    # 工作流
    wdir = paths.WORKFLOW_DIR
    for f in sorted(wdir.glob("*.json")) if wdir.exists() else []:
        wf_id = "chat/" + f.stem.replace("chat_", "", 1) if f.stem.startswith("chat_") else f.stem
        try:
            wf = json.loads(f.read_text(encoding="utf-8"))
            k.put_workflow(wf_id, wf)
            print("  [写入] 工作流 %s（%d 个块）" % (wf_id, len(wf.get("blocks", []))))
        except Exception as e:
            print("  [失败] %s：%s" % (f.name, str(e)[:120]))

    # 插件
    need = {"im_onebot_adapters", "scheduler", "api_collection"}
    try:
        plugins = k.list_plugins()
        have = {p.get("name") for p in plugins}
        enabled = {p.get("name") for p in plugins if p.get("is_enabled")}
        for n in sorted(need):
            if n not in have:
                print("  [!] 插件 %s 没安装：pip install chatgpt-mirai-qq-bot-%s"
                      % (n, n.replace("_", "-")))
            elif n not in enabled:
                try:
                    k.enable_plugin(n)
                    print("  [启用] 插件 %s" % n)
                except Exception as e:
                    print("  [!] 启用 %s 失败：%s" % (n, str(e)[:100]))
            else:
                print("  [ok] 插件 %s 已启用" % n)
    except Exception as e:
        print("  [!] 查插件失败：%s" % str(e)[:120])

    # 自测：不依赖 QQ，走内置 http_legacy 通道
    print("\n  --- 自测（私聊链路，用假会话 id 不污染真实记忆）---")
    if not _port_open(paths.gallery_port()):
        print("  [!] 图库服务没起（端口 %d），发表情包会失败。先跑 scripts\\启动图库.cmd"
              % paths.gallery_port())
    for msg, sid, note in [
        ("在吗", "friend-provision-selftest", "基本对话"),
        ("发个表情包", "friend-provision-selftest", "工具+图库"),
    ]:
        try:
            t0 = time.time()
            d = k.chat(msg, sid)
            txt = " / ".join(str(m)[:60] for m in d.get("message", []))
            print("  [%s] %.1fs 图%d张 -> %s" % (note, time.time() - t0, len(d.get("image", [])), txt))
        except Exception as e:
            print("  [%s] 失败：%s" % (note, str(e)[:140]))


def main():
    args = sys.argv[1:]
    if "--online" in args:
        online()
    elif "--offline" in args:
        offline()
    else:
        offline()
        online()


if __name__ == "__main__":
    main()
