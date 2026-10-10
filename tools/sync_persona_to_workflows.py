# -*- coding: utf-8 -*-
"""把 persona/ 的两份文件同步进config/workflows/*.json 的system_prompt。

为什么要这个脚本：
  config/workflows/*.json 是安装时灌进 kirara 的模板。如果模板里的
  system_prompt 和 persona/ 下的文件不同步，就会出现
  「改了人设但机器人没变」或者「仓库里的示例和实际行为不一致」。

用法：
  python tools/sync_persona_to_workflows.py          # 写入
  python tools/sync_persona_to_workflows.py --check  # 只校验不写（CI 用）

注意：写回时保持 indent=1、不留末尾换行，和仓库里原有的排版一致。
"""
import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bot"))

import paths  # noqa: E402

# 会被同步的工作流模板，以及它们该有的名字/描述
TARGETS = {
    "chat_tools.json": {
        "name": "聊天 - 表情包、搜索与定时",
        "description": "私聊/群聊主力：自定义人设 + 视觉模型 + 主动发表情包/联网搜索/定时提醒",
    },
    "chat_normal_multimodal.json": {
        "name": "聊天 - 多模态（看得懂图）",
        "description": "备用：纯多模态图文对话。默认走chat/tools，这里留作对照",
    },
}

# 工具决策可用块。搜索类需要 web_search 插件（安装脚本会装）。
# 决策调用每条消息都跑一次，别把贵的模型放这里。
TOOL_BLOCKS = [
    "random_emoji",
    "sougou_image_search",
    "web_search_by_keyword",
    "weather_search",
    "create_task",
    "create_one_time_task",
    "get_tasks",
    "delete_task",
    "delete_all_tasks",
]


def dump(obj):
    """和仓库原有排版保持一致：indent=1、末尾不带换行。"""
    return json.dumps(obj, ensure_ascii=False, indent=1)


def sync(check_only=False):
    system_prompt = paths.build_system_prompt()
    changed = []
    for fname, meta in TARGETS.items():
        p = paths.WORKFLOW_DIR / fname
        if not p.exists():
            print("  [跳过] 找不到 %s" % p)
            continue
        raw = p.read_text(encoding="utf-8")
        wf = json.loads(raw)

        before = raw
        wf["name"] = meta["name"]
        wf["description"] = meta["description"]
        for b in wf.get("blocks", []):
            if b.get("name") == "system_prompt":
                b.setdefault("config", {})["text"] = system_prompt
            elif b.get("type_name") == "auto:auto_execute_tools":
                b.setdefault("config", {})["available_block_names"] = ",".join(TOOL_BLOCKS)

        after = dump(wf)
        if before == after:
            print("  [一致] %s" % fname)
            continue
        changed.append(fname)
        if check_only:
            print("  [不一致] %s（system_prompt 或工具列表与 persona/ 不同步）" % fname)
        else:
            with io.open(p, "w", encoding="utf-8", newline="") as f:
                f.write(after)
            print("  [写入] %s  system_prompt %d 字" % (fname, len(system_prompt)))

    print()
    print("可用工具：%s" % ",".join(TOOL_BLOCKS))
    if check_only:
        if changed:
            print("校验失败：%s 与 persona/ 不同步，请运行 python tools/sync_persona_to_workflows.py"
                  % "、".join(changed))
            return 1
        print("校验通过：工作流模板与 persona/ 完全同步。")
    else:
        print("完成，共更新 %d 个模板。" % len(changed))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验不写入")
    args = ap.parse_args()
    try:
        return sync(check_only=args.check)
    except (FileNotFoundError, ValueError) as e:
        sys.exit("人设有问题：%s" % e)


if __name__ == "__main__":
    sys.exit(main())
