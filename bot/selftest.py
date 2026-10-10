# -*- coding: utf-8 -*-
"""端到端自测：不依赖 QQ 也能验证整条链路。

走的是 kirara 内置 http_legacy 适配器的 POST /v1/chat，
session_id 用假的（friend-selftest-* / group-selftest:*），不会污染真实会话记忆。

用法：python bot\\selftest.py     （或双击 scripts\\自测.cmd）
"""
import json
import sys
import time
import urllib.request

import paths
from kirara_api import Kirara, KiraraError

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print("  [%s] %-22s %s" % ("通过" if ok else "失败", name, detail))


def http_json(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print("=" * 62)
    print("  小喵 QQ 机器人 · 自测")
    print("=" * 62)

    # 1. 图库服务
    try:
        d = http_json(paths.gallery_url() + "/health")
        check("图库服务", d.get("ok") is True, paths.gallery_url())
    except Exception as e:
        check("图库服务", False, "连不上 %s（%s）—— 先跑 scripts\\启动图库.cmd"
              % (paths.gallery_url(), type(e).__name__))

    # 2. 图库有没有货
    try:
        lst = http_json(paths.gallery_url() + "/list")
        total = sum(lst.values())
        check("图库张数", total > 0, "共 %d 张：%s" % (total, json.dumps(lst, ensure_ascii=False)))
    except Exception as e:
        check("图库张数", False, str(e)[:60])

    # 3. 收录器
    try:
        s = http_json(paths.gallery_url() + "/stolen")
        check("自动收录", True, "已收 %s 张，打标 %s 张" % (s.get("已收录"), s.get("已打标")))
    except Exception as e:
        check("自动收录", False, str(e)[:60])

    # 4. kirara
    k = Kirara()
    try:
        k.wait_boot(timeout=60)
        check("kirara 登录", True, paths.KIRARA_BASE)
    except Exception as e:
        check("kirara 登录", False, str(e)[:150])
        print("\n  kirara 没起来，后面的项目跳过。")
        return summary()

    # 5. 插件
    try:
        plugins = {p.get("name"): p.get("is_enabled") for p in k.list_plugins()}
        need = ["im_onebot_adapters", "scheduler", "api_collection"]
        missing = [n for n in need if not plugins.get(n)]
        check("必要插件", not missing, "缺失/未启用：%s" % missing if missing else "onebot+scheduler+api_collection 都在线")
    except Exception as e:
        check("必要插件", False, str(e)[:80])

    # 6. 派发规则：私聊/群聊是否指向带工具的工作流
    try:
        rules = {r["rule_id"]: r for r in k.get_rules()}
        pc = rules.get("chat_creative", {}).get("workflow_id")
        gp = rules.get("chat_normal", {}).get("workflow_id")
        check("派发规则", pc == "chat:tools" and gp == "chat:tools",
              "私聊->%s，群聊->%s" % (pc, gp))
    except Exception as e:
        check("派发规则", False, str(e)[:80])

    # 7. 视觉模型是否配好
    try:
        cfg = (paths.kirara_data_dir() / "config.yaml").read_text(encoding="utf-8")
        has_vision = "deepseek-v4-flash-vision-exp" in cfg
        has_key = "api_key: sk-" in cfg and "${" not in cfg.split("api_key:")[1][:60]
        check("视觉模型", has_vision, "deepseek-v4-flash-vision-exp %s" % ("已配置" if has_vision else "未配置"))
        check("API Key", has_key, "已填入" if has_key else "还是占位符，请检查 .env 与 config.yaml")
    except Exception as e:
        check("模型配置", False, str(e)[:80])

    # 8. 对话与人设
    print("\n  --- 对话实测 ---")
    for msg, sid, want_persona in [
        ("在吗", "friend-selftest-1", True),
        ("发个表情包", "friend-selftest-1", False),
        ("哈哈哈哈笑死我了", "group-selftest:10001", False),
    ]:
        label = "群聊" if sid.startswith("group-") else "私聊"
        try:
            t0 = time.time()
            d = k.chat(msg, sid)
            txt = " / ".join(str(m)[:70] for m in d.get("message", []))
            imgs = len(d.get("image", []))
            leak = [w for w in ["系统", "工具", "[表情包]", "{", "AI", "模型"] if w in txt]
            ok = bool(txt.strip()) and not leak
            if "表情包" in msg:
                ok = ok and imgs > 0
            check("%s·%s" % (label, msg[:8]), ok,
                  "%.1fs 图%d张%s | %s" % (time.time() - t0, imgs,
                                          "  ⚠️出戏词:" + ",".join(leak) if leak else "", txt))
        except KiraraError as e:
            check("%s·%s" % (label, msg[:8]), False, str(e)[:120])
        except Exception as e:
            check("%s·%s" % (label, msg[:8]), False, "%s: %s" % (type(e).__name__, str(e)[:90]))

    return summary()


def summary():
    bad = [r for r in RESULTS if not r[1]]
    print()
    print("=" * 62)
    if not bad:
        print("  全部 %d 项通过。机器人可以用了。" % len(RESULTS))
    else:
        print("  %d 项通过，%d 项失败：" % (len(RESULTS) - len(bad), len(bad)))
        for name, _ok, detail in bad:
            print("    - %s：%s" % (name, detail))
    print("=" * 62)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
