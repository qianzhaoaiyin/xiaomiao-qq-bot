# -*- coding: utf-8 -*-
"""配置与补丁的单元测试：确保仓库里的模板自身是正确的、且不含密钥。

这些断言看起来琐碎，但它们守的是最容易出事的地方：
把真实 key 提交上去、模板里的模型名写错、规则指向不存在的工作流。
"""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bot"))

import paths  # noqa: E402
import patch_humanize_send as phs  # noqa: E402
import patch_person_memory as ppm  # noqa: E402
import patch_sticker_source as pss  # noqa: E402
import watchdog  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None


class EnvTest(unittest.TestCase):
    def test_读取env并忽略注释与空行(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / ".env"
            f.write_text("# 注释\n\nDEEPSEEK_API_KEY=sk-test123\n OWNER_QQ = 10001 \n"
                         "GALLERY_PORT=3999\n没有等号的行\n", encoding="utf-8")
            old = paths.ENV_FILE
            paths.ENV_FILE = f
            try:
                env = paths.load_env()
                self.assertEqual(env["DEEPSEEK_API_KEY"], "sk-test123")
                self.assertEqual(env["OWNER_QQ"], "10001", "等号两边的空格要去掉")
                self.assertEqual(paths.gallery_port(), 3999)
            finally:
                paths.ENV_FILE = old

    def test_默认端口(self):
        self.assertEqual(paths.DEFAULT_GALLERY_PORT, 3100)


class KiraraConfigTest(unittest.TestCase):
    def setUp(self):
        self.text = (paths.CONFIG_DIR / "kirara.config.yaml").read_text(encoding="utf-8")

    def test_不含真实密钥(self):
        self.assertNotRegex(self.text, r"sk-[A-Za-z0-9]{16,}", "模板里绝不能有真实 key")
        self.assertIn("${DEEPSEEK_API_KEY}", self.text)

    def test_握手口令走占位符(self):
        self.assertIn("${ONEBOT_TOKEN}", self.text)
        self.assertNotIn("KiraraQQ2026", self.text, "本机握手口令不该提交进仓库")

    def test_视觉模型已配置(self):
        self.assertIn("deepseek-v4-flash-vision-exp", self.text, "没有视觉模型就看不懂表情包")

    def test_默认模型不是上游那个不存在的(self):
        # 注意：只检查真正生效的 llm_model 值，注释里提到旧值是正常的
        m = re.search(r"^\s*llm_model:\s*(\S+)", self.text, re.M)
        self.assertIsNotNone(m, "没找到 defaults.llm_model")
        self.assertNotEqual(m.group(1), "gemini-1.5-flash",
                            "上游模板的默认模型指向未配置的后端，会让未指定模型的块报错")
        self.assertEqual(m.group(1), "deepseek-flash")

    @unittest.skipIf(yaml is None, "没装 pyyaml")
    def test_可被yaml解析(self):
        d = yaml.safe_load(self.text)
        self.assertIn("ims", d)
        self.assertIn("llms", d)
        adapters = [i["adapter"] for i in d["ims"]]
        self.assertIn("onebot", adapters, "必须有 onebot 适配器才能接 NapCat")


class RulesTest(unittest.TestCase):
    def _load(self, name):
        p = paths.CONFIG_DIR / name
        self.assertTrue(p.exists(), "缺少 %s" % name)
        return p.read_text(encoding="utf-8")

    @unittest.skipIf(yaml is None, "没装 pyyaml")
    def test_两份规则都能解析(self):
        for name in ("rules.yaml", "rules.owner.yaml"):
            d = yaml.safe_load(self._load(name))
            self.assertIsInstance(d, list)
            for r in d:
                self.assertIn("rule_id", r)
                self.assertIn("workflow_id", r)
                self.assertTrue(r.get("rule_groups"), "%s 缺 rule_groups" % r["rule_id"])

    def test_严格模式含占位符且三条关键规则齐全(self):
        t = self._load("rules.owner.yaml")
        self.assertIn("${OWNER_QQ}", t, "provision 靠这个占位符注入主人 QQ")
        for rid in ("owner_private", "stranger_private", "group_active"):
            self.assertIn("rule_id: %s" % rid, t)
        self.assertIn("chat:memory_store", t, "陌生人私聊要静默，不能回消息")

    def test_替换后仍是合法yaml且主人号被写入(self):
        t = self._load("rules.owner.yaml").replace("${OWNER_QQ}", "10001")
        self.assertNotIn("${", t)
        if yaml:
            d = yaml.safe_load(t)
            owner = next(r for r in d if r["rule_id"] == "owner_private")
            ids = [x["config"].get("sender_id") for g in owner["rule_groups"] for x in g["rules"]]
            self.assertIn("10001", ids)
            # 主人私聊优先级必须高于陌生人规则，否则会被静默掉
            stranger = next(r for r in d if r["rule_id"] == "stranger_private")
            self.assertGreater(owner["priority"], stranger["priority"])

    def test_宽松模式也保留(self):
        t = self._load("rules.yaml")
        self.assertIn("chat:tools", t)


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        p = paths.WORKFLOW_DIR / "chat_tools.json"
        self.assertTrue(p.exists())
        self.wf = json.loads(p.read_text(encoding="utf-8"))
        self.blocks = {b["name"]: b for b in self.wf["blocks"]}

    def test_回复用视觉模型_决策用便宜模型(self):
        self.assertEqual(self.blocks["llm_chat"]["config"].get("model_name"),
                         "deepseek-v4-flash-vision-exp")
        self.assertEqual(self.blocks["tools"]["config"].get("model_name"), "deepseek-flash",
                         "每条消息都要调一次决策，必须用便宜模型")

    def test_工具齐全(self):
        names = self.blocks["tools"]["config"]["available_block_names"]
        for need in ("random_emoji", "sougou_image_search", "create_task"):
            self.assertIn(need, names)

    def test_搜索与天气工具已挂上(self):
        # 卡片里明确要求「不懂就搜、别瞎答」，没有搜索工具这条人设是空话
        names = self.blocks["tools"]["config"]["available_block_names"]
        self.assertIn("web_search_by_keyword", names)
        self.assertIn("weather_search", names)

    def test_人设与提示词铁律都在(self):
        sp = self.blocks["system_prompt"]["config"]["text"]
        self.assertIn("鲸鱼娘", sp, "人设没灌进去")
        self.assertIn("{memory_content}", sp, "记忆占位符丢了机器人就会失忆")
        self.assertIn("{current_date_time}", sp)
        self.assertIn("发表情包", sp)
        self.assertIn("气氛到了就主动发一张", sp, "没有「主动发图」的规则，它就得等你开口要")
        self.assertIn("铁律", sp, "没有铁律它会说出'系统塞给我的'这种出戏话")
        self.assertIn("方括号占位符", sp, "不禁就会在正文里打 [表情包]")
        self.assertIn("明确开口要图", sp, "没有这条例外，它会连你的正当要求一起拒绝")
        self.assertIn("联网搜索", sp, "没告诉它有搜索工具，它不会去查")
        self.assertIn("`<break>`", sp, "没有分段规则，它会把三句话塞进一个气泡")

    def test_图片默认不解读(self):
        # 这是人设里优先级最高的一条：别人发图/发表情包时当没看见，
        # 只有对方在文字里明确要求看图才解读。少了它机器人会秒变图片解说员。
        sp = self.blocks["system_prompt"]["config"]["text"]
        self.assertIn("默认当作没看见内容", sp)
        self.assertIn("唯一的例外", sp)

    def test_不含真实密钥或个人QQ号(self):
        raw = json.dumps(self.wf, ensure_ascii=False)
        self.assertNotRegex(raw, r"sk-[A-Za-z0-9]{16,}")
        self.assertNotRegex(raw, r"KiraraQQ\d{4}", "OneBot 握手口令不该写死在模板里")


class PersonaSyncTest(unittest.TestCase):
    """工作流模板里的 system_prompt 必须和 persona/ 下的文件一致。

    不一致的后果：改了人设文件但机器人没变，或者仓库示例和实际行为对不上。
    """

    def test_两份人设文件都在(self):
        self.assertTrue(paths.PERSONA_FILE.exists(), "缺少 persona/人设.txt")
        self.assertTrue(paths.TOOLS_FILE.exists(), "缺少 persona/工具段.txt")

    def test_工具段含必需占位符(self):
        for ph in paths.REQUIRED_PLACEHOLDERS:
            self.assertIn(ph, paths.TOOLS_FILE.read_text(encoding="utf-8"),
                          "工具段缺少占位符 %s，工作流会跑不起来" % ph)

    def test_缺占位符时构造会报错而不是写出坏配置(self):
        good = paths.TOOLS_FILE.read_text(encoding="utf-8")
        try:
            paths.build_system_prompt()
            with self.assertRaises(ValueError):
                paths.TOOLS_FILE.write_text(good.replace("{memory_content}", ""), encoding="utf-8")
                paths.build_system_prompt()
        finally:
            paths.TOOLS_FILE.write_text(good, encoding="utf-8")

    def test_模板与人设同步(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sync_persona_to_workflows.py"), "--check"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         "工作流模板与人设不同步，跑 python tools/sync_persona_to_workflows.py\n%s"
                         % (r.stdout + r.stderr)[-500:])


class NapCatConfigTest(unittest.TestCase):
    def test_握手口令用占位符(self):
        p = paths.CONFIG_DIR / "napcat.onebot11.json"
        self.assertTrue(p.exists(), "缺少 %s" % p)
        text = p.read_text(encoding="utf-8")
        self.assertIn("${ONEBOT_TOKEN}", text, "口令必须走占位符，不能写死")
        self.assertNotIn("KiraraQQ2026", text)

    def test_env示例里有口令项(self):
        text = (paths.ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("ONEBOT_TOKEN", text)


class PatchTest(unittest.TestCase):
    """图源补丁必须幂等，且不能把插件其它方法弄坏。"""

    SRC = (
        "import aiohttp\n\n\nclass ApiCollection:\n"
        "    async def _fabiaoqing_image(self, keyword: str) -> str:\n"
        "        return 'https://old.dead/api'\n\n"
        "    async def get_random_emoji(self) -> str:\n"
        "        return await self._fabiaoqing_image('x')\n\n"
        "    async def get_sougou_image(self, keyword: str) -> str:\n"
        "        return await self._fabiaoqing_image(keyword)\n\n"
        "    async def weacherSearch(self, city: str) -> str:\n"
        "        return city\n"
    )

    def _fake_pkg(self):
        d = Path(tempfile.mkdtemp())
        pkg = d / "api_collection"
        pkg.mkdir()
        (pkg / "api_collection.py").write_text(self.SRC, encoding="utf-8")
        return d

    def test_打补丁_幂等_不破坏其它方法(self):
        d = self._fake_pkg()
        old = paths.site_packages
        paths.site_packages = lambda: d
        try:
            self.assertTrue(pss.patch(verbose=False), "首次应该真的改")
            self.assertFalse(pss.patch(verbose=False), "第二次必须是 no-op")
            text = (d / "api_collection" / "api_collection.py").read_text(encoding="utf-8")
            self.assertIn("本地表情包图库", text)
            self.assertNotIn("old.dead", text, "旧图源应被替换掉")
            self.assertIn("weacherSearch", text, "不能把无关方法一起删了")
            import py_compile
            py_compile.compile(str(d / "api_collection" / "api_collection.py"), doraise=True)
            backups = list((d / "api_collection").glob("*.orig-*"))
            self.assertEqual(len(backups), 1, "应该留下且只留下一份备份")
        finally:
            paths.site_packages = old


# 下面是两个新补丁的夹具：内容取自**打补丁之前**的上游源码。
# 只测"补丁能打上去"是不够的——还得测幂等、语法、以及打完之后行为是对的。
ORIG_ADAPTER_HEAD = """from typing import Dict, Optional, Set, Any, List
import asyncio
import functools
import random
import time
from urllib.parse import urlparse
"""

ORIG_FLUSH = """                # 计算延时
                duration = max(text_length * 0.1, 1) + random.uniform(0.5, 1.5)
                await asyncio.sleep(duration)"""

# 缩进必须和真实上游一致：flush 的 body 在 16 空格、发送循环在 12 空格。
# 否则夹具本身就语法错误，测的就不是补丁了。
ORIG_CLASS = '''class OneBotAdapter:
    async def send_message(self):
        text_length = 0
        async def flush():
            nonlocal text_length
            if not buffer:
                return
                # 计算延时
                duration = max(text_length * 0.1, 1) + random.uniform(0.5, 1.5)
                await asyncio.sleep(duration)
            for segment in segments:
                # 判断是否需要flush
                if segment.type in ("text", "record", "video", "rps", "dice", "shake", "poke", "share", "contact", "location"):
                    await flush()
                    buffer = [segment]
                    if segment.type == "text":
                        text_length = len(segment.data.get("text", ""))
'''

ORIG_SCOPES = '''from kirara_ai.im.sender import ChatSender, ChatType

from .base import MemoryScope


class MemberScope(MemoryScope):
    """群成员作用域"""

    def get_scope_key(self, sender: ChatSender) -> str:
        if sender.chat_type == ChatType.GROUP:
            return f"member:{sender.group_id}:{sender.user_id}"
        else:
            return f"c2c:{sender.user_id}"

    def is_in_scope(self, target_sender, query_sender) -> bool:
        if target_sender.chat_type != query_sender.chat_type:
            return False
        return target_sender.user_id == query_sender.user_id


class GlobalScope(MemoryScope):
    """全局作用域"""

    def get_scope_key(self, sender):
        return "global"

    def is_in_scope(self, target_sender, query_sender) -> bool:
        return True
'''

ORIG_SCOPES_INIT = """from .base import MemoryScope
from .builtin_scopes import GlobalScope, GroupScope, MemberScope

__all__ = ["MemoryScope", "MemberScope", "GroupScope", "GlobalScope"]
"""

ORIG_ENTRY = """from kirara_ai.memory.scopes import GlobalScope, GroupScope, MemberScope


def setup():
    memory_manager.register_scope("member", MemberScope)
    memory_manager.register_scope("group", GroupScope)
    memory_manager.register_scope("global", GlobalScope)
"""

WF = """blocks:
  - type: internal:chat_memory_query
    name: query_memory
    params:
      scope_type: group
  - type: internal:chat_memory_store
    name: memory_store
    params:
      scope_type: group
  - type: internal:chat_completion
    name: llm
    params:
      model_name: deepseek-flash
"""


class HumanizePatchTest(unittest.TestCase):
    def _fake(self):
        d = Path(tempfile.mkdtemp())
        pkg = d / "im_onebot_adapters"
        pkg.mkdir()
        (pkg / "adapter.py").write_text(
            ORIG_ADAPTER_HEAD + "\n" + ORIG_CLASS, encoding="utf-8")
        return d

    def test_幂等且语法正确(self):
        d = self._fake()
        old = paths.site_packages
        paths.site_packages = lambda: d
        try:
            self.assertTrue(phs.patch(verbose=False), "首次应该真的改")
            self.assertFalse(phs.patch(verbose=False), "第二次必须是 no-op")
            import py_compile
            py_compile.compile(str(d / "im_onebot_adapters" / "adapter.py"), doraise=True)
            self.assertEqual(len(list((d / "im_onebot_adapters").glob("*.orig-*"))), 1,
                             "应该留下且只留下一份备份")
        finally:
            paths.site_packages = old

    def test_补丁后行为正确(self):
        d = self._fake()
        old = paths.site_packages
        paths.site_packages = lambda: d
        try:
            phs.patch(verbose=False)
            text = (d / "im_onebot_adapters" / "adapter.py").read_text(encoding="utf-8")
            self.assertIn("def humanize_delay", text)
            self.assertIn("HUMANIZE_MAX_SEGMENTS", text, "没有条数上限，模型一激动能刷爆群")
            self.assertIn("HUMANIZE_NIGHT_FACTOR", text, "没有深夜变慢")
            self.assertIn("sent_groups", text, "条数上限没接进发送循环")
            # 辅助函数必须在 class 之前，否则 class 里引用不到
            self.assertLess(text.index("def humanize_delay"), text.index("class OneBotAdapter"))
            # 逐个采样，确认确实产生了长停顿
            head = text[:text.index("class OneBotAdapter")]
            ns = {"__name__": "adapter_head"}
            exec(compile(head, "adapter_head", "exec"), ns)
            ds = [ns["humanize_delay"](6) for _ in range(300)]
            self.assertGreater(max(ds), 3.0, "300 次采样里至少要出现一次长停顿（>3秒）")
            self.assertLessEqual(max(ds), ns["HUMANIZE_MAX_DELAY"], "不能超过封顶值")
        finally:
            paths.site_packages = old

    def test_结构对不上时明确报错而不是乱改(self):
        d = self._fake()
        (d / "im_onebot_adapters" / "adapter.py").write_text("# 结构完全不一样\n", encoding="utf-8")
        old = paths.site_packages
        paths.site_packages = lambda: d
        try:
            with self.assertRaises(SystemExit):
                phs.patch(verbose=False)
        finally:
            paths.site_packages = old


class PersonMemoryPatchTest(unittest.TestCase):
    def _fake(self):
        d = Path(tempfile.mkdtemp())
        sp = d / "site-packages"
        (sp / "kirara_ai" / "memory" / "scopes").mkdir(parents=True)
        (sp / "kirara_ai").mkdir(exist_ok=True)
        (sp / "kirara_ai" / "memory" / "scopes" / "builtin_scopes.py").write_text(
            ORIG_SCOPES, encoding="utf-8")
        (sp / "kirara_ai" / "memory" / "scopes" / "__init__.py").write_text(
            ORIG_SCOPES_INIT, encoding="utf-8")
        (sp / "kirara_ai" / "entry.py").write_text(ORIG_ENTRY, encoding="utf-8")
        return d

    def test_幂等_语法正确_工作流也被改了(self):
        d = self._fake()
        sp = d / "site-packages"
        wfdir = d / "data" / "workflows" / "chat"
        wfdir.mkdir(parents=True)
        (wfdir / "tools.yaml").write_text(WF, encoding="utf-8")

        old_sp, old_data = paths.site_packages, paths.kirara_data_dir
        paths.site_packages = lambda: sp
        paths.kirara_data_dir = lambda: d / "data"
        try:
            self.assertTrue(ppm.patch(verbose=False), "首次应该真的改")
            self.assertFalse(ppm.patch(verbose=False), "第二次必须是 no-op")
            import py_compile
            for rel in ("kirara_ai/memory/scopes/builtin_scopes.py",
                        "kirara_ai/memory/scopes/__init__.py",
                        "kirara_ai/entry.py"):
                py_compile.compile(str(sp / rel), doraise=True)
            # 工作流里的记忆块必须一起改——只改 config.yaml 是没用的
            got = (wfdir / "tools.yaml").read_text(encoding="utf-8")
            self.assertEqual(got.count("scope_type: person"), 2,
                             "两个记忆块都要改成 person")
            self.assertNotIn("scope_type: group", got)
        finally:
            paths.site_packages, paths.kirara_data_dir = old_sp, old_data

    def test_PersonScope真的跨场合且不串人(self):
        """直接验证作用域类本身，而不只是检查文件里有没有那个字符串。"""
        import types

        class FakeChatType:
            GROUP, C2C = "group", "c2c"

        class FakeSender:
            def __init__(self, user_id, chat_type, group_id=None):
                self.user_id, self.chat_type, self.group_id = user_id, chat_type, group_id

        ns = types.ModuleType("fake")
        ns.__dict__["__name__"] = "fake_scopes"
        # 去掉相对导入，夹具里没法建包
        src = (ORIG_SCOPES + ppm.PERSON_SCOPE).replace("from .base import MemoryScope", "")
        exec(compile(src, "scopes", "exec"),
             {"__name__": "fake_scopes",
              "ChatSender": FakeSender, "ChatType": FakeChatType,
              "MemoryScope": type("MemoryScope", (), {})}, ns.__dict__)
        ps = ns.PersonScope()
        c2c = FakeSender("10001", "c2c")
        grp = FakeSender("10001", "group", "999")
        other = FakeSender("20002", "c2c")

        self.assertEqual(ps.get_scope_key(c2c), ps.get_scope_key(grp),
                         "同一个人的私聊和群聊必须落在同一个桶")
        self.assertTrue(ps.is_in_scope(c2c, grp), "私聊记忆群里的自己应该能读到")
        self.assertTrue(ps.is_in_scope(grp, c2c), "群里记忆私聊的自己应该能读到")
        self.assertFalse(ps.is_in_scope(other, c2c), "不能读到别人，否则是隐私泄露")

        ms = ns.MemberScope()
        self.assertFalse(ms.is_in_scope(grp, c2c),
                         "旧的 member 作用域本来就不跨场合（这是补丁要解决的原因）")


class WatchdogSafetyTest(unittest.TestCase):
    def test_熔断参数是保守值(self):
        # 这三个数字是拿真账号被限速的教训定的，别让人随手调大
        self.assertEqual(watchdog.FAIL_STRIKES, 3)
        self.assertGreaterEqual(watchdog.COOLDOWN_SEC, 300)
        self.assertGreaterEqual(watchdog.BOOT_WAIT_SEC, 30)

    def test_熔断_三次失败后停止重试(self):
        import time as _t
        watchdog._breaker.clear()
        self.assertTrue(watchdog.breaker_allow("kirara"))
        self.assertTrue(watchdog.breaker_fail("X"))
        self.assertTrue(watchdog.breaker_fail("X"))
        self.assertFalse(watchdog.breaker_fail("X"), "第三次失败就该熔断")
        self.assertFalse(watchdog.breaker_allow("X"), "熔断期间不允许重试")
        watchdog._breaker["X"]["open_until"] = _t.time() - 1
        self.assertTrue(watchdog.breaker_allow("X"), "冷却结束后自动恢复")
        watchdog._breaker.clear()

    def test_成功一次就清零(self):
        watchdog._breaker.clear()
        watchdog.breaker_fail("Y")
        watchdog.breaker_ok("Y")
        self.assertEqual(watchdog._breaker["Y"]["strikes"], 0)
        watchdog._breaker.clear()

    def test_藏窗口只针对控制台类(self):
        self.assertIn("ConsoleWindowClass", watchdog._CONSOLE_CLASSES)
        self.assertIn("PseudoConsoleWindow", watchdog._CONSOLE_CLASSES)

    def test_自启命令用pythonw(self):
        cmd = paths.autostart_command()
        self.assertIn("watchdog.py", cmd)
        if os.name == "nt" and "pythonw" in paths.find_python().lower():
            self.assertIn("pythonw", cmd, "自启必须用 pythonw，否则开机弹黑窗")


if __name__ == "__main__":
    unittest.main()
