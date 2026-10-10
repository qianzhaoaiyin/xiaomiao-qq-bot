# -*- coding: utf-8 -*-
"""收录器的单元测试：重点是那几条过滤规则（写错就会把机器人自己发的图偷回来）。

不需要 kirara / 网络；视觉打标被替换成假实现。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bot"))

import sticker_collector as sc  # noqa: E402


def _img(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.media = self.tmp / "media"
        self.gallery = self.tmp / "表情包"
        # 重定向模块级路径
        self._old = (sc.MEDIA_DIR, sc.GALLERY, sc.STOLEN, sc.INDEX, sc.MAX_BYTES)
        sc.MEDIA_DIR = self.media
        sc.GALLERY = self.gallery
        sc.STOLEN = self.gallery / "偷来的"
        sc.INDEX = sc.STOLEN / ".index.json"
        sc.MAX_BYTES = 1_500_000
        sc.vision_tag = lambda p: {"mood": "搞笑", "keywords": ["猫", "沙雕"], "raw": "x", "tokens": 1}

    def tearDown(self):
        sc.MEDIA_DIR, sc.GALLERY, sc.STOLEN, sc.INDEX, sc.MAX_BYTES = self._old

    def _media(self, mid, payload, source="im_message", refs=None, fmt="png", mtype="image"):
        (self.media / "files").mkdir(parents=True, exist_ok=True)
        (self.media / "metadata").mkdir(parents=True, exist_ok=True)
        _img(self.media / "files" / ("%s.%s" % (mid, fmt)), payload)
        (self.media / "metadata" / (mid + ".json")).write_text(json.dumps({
            "media_id": mid, "source": source, "media_type": mtype,
            "references": refs if refs is not None else ["memory:group:10001"],
            "format": fmt, "created_at": "2026-10-10T10:00:00",
        }, ensure_ascii=False), encoding="utf-8")

    def test_收到的图片会被收录并打标(self):
        self._media("a" * 40, b"\x89PNG-fake-1")
        n = sc.scan_once()
        self.assertEqual(n, 1)
        s = sc.summary()
        self.assertEqual(s["已收录"], 1)
        self.assertEqual(s["已打标"], 1)
        name = s["最近"][0]["文件"]
        self.assertIn("搞笑", name, "标签要写进文件名，之后才能按关键词检索")
        self.assertIn("猫", name)
        self.assertTrue(name.endswith(".png"))

    def test_同一张图不会重复收录(self):
        self._media("b" * 40, b"\x89PNG-fake-2")
        sc.scan_once()
        self.assertEqual(sc.scan_once(), 0, "第二次扫描不该再收")
        self.assertEqual(sc.summary()["已收录"], 1)

    def test_机器人自己发出的图不会被偷回来(self):
        # 图库里已经有同样内容的图（就是我们发出去的那张）
        _img(self.gallery / "开心" / "已有.png", b"\x89PNG-fake-3")
        import hashlib
        mid = hashlib.sha1(b"\x89PNG-fake-3").hexdigest()
        self._media(mid, b"\x89PNG-fake-3")
        self.assertEqual(sc.scan_once(), 0, "内容 sha1 命中图库就该跳过")
        idx = json.loads(sc.INDEX.read_text(encoding="utf-8"))
        self.assertIn("图库发出去", idx[mid]["skip"])

    def test_无会话来源的跳过(self):
        self._media("c" * 40, b"\x89PNG-fake-4", refs=[])
        self.assertEqual(sc.scan_once(), 0)

    def test_非图片消息跳过(self):
        self._media("d" * 40, b"x", mtype="voice")
        self.assertEqual(sc.scan_once(), 0)

    def test_超大图当照片处理不收(self):
        sc.MAX_BYTES = 10
        self._media("e" * 40, b"0123456789ABCDEF")
        self.assertEqual(sc.scan_once(), 0)
        self.assertEqual(sc.summary()["跳过大图"], 1)

    def test_打标失败也要收录(self):
        sc.vision_tag = lambda p: None
        self._media("f" * 40, b"\x89PNG-fake-6")
        self.assertEqual(sc.scan_once(), 1)
        self.assertIn("未打标", sc.summary()["最近"][0]["文件"])

    def test_来源会话被记录(self):
        self._media("1" * 40, b"\x89PNG-fake-7", refs=["memory:group:777"])
        sc.scan_once()
        self.assertEqual(sc.summary()["按来源"].get("group:777"), 1)


if __name__ == "__main__":
    unittest.main()
