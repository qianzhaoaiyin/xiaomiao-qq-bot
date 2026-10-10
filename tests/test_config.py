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
import patch_sticker_source as pss  # noqa: E402

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

    def test_人设与提示词铁律都在(self):
        sp = self.blocks["system_prompt"]["config"]["text"]
        self.assertIn("猫娘", sp)
        self.assertIn("{memory_content}", sp, "记忆占位符丢了机器人就会失忆")
        self.assertIn("{current_date_time}", sp)
        self.assertIn("主动发表情包", sp)
        self.assertIn("铁律", sp, "没有铁律它会说出'系统塞给我的'这种出戏话")
        self.assertIn("方括号占位符", sp, "不禁就会在正文里打 [表情包]")
        self.assertIn("明确开口要图", sp, "没有这条例外，它会连你的正当要求一起拒绝")

    def test_不含真实密钥或个人QQ号(self):
        raw = json.dumps(self.wf, ensure_ascii=False)
        self.assertNotRegex(raw, r"sk-[A-Za-z0-9]{16,}")


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


if __name__ == "__main__":
    unittest.main()
