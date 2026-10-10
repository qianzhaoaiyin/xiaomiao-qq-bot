# -*- coding: utf-8 -*-
"""图库服务的单元测试：关键词命中、回退策略、URL 生成。

跑法（仓库根目录）：
    python -m unittest discover -s tests -v
不需要 kirara / NapCat / 网络。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot"))

import gallery_server as gs  # noqa: E402


def _png(path, size=64):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * size)


class GalleryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._old_root = gs.ROOT
        gs.ROOT = self.tmp
        _png(self.tmp / "开心" / "哈哈大笑.png")
        _png(self.tmp / "晚安" / "晚安喵.gif")
        _png(self.tmp / "偷来的" / "20261010_abcd1234_搞笑示爱_爱心_表白.png")
        (self.tmp / "开心" / "说明.txt").write_text("非图片文件", encoding="utf-8")

    def tearDown(self):
        gs.ROOT = self._old_root

    def test_空目录返回空(self):
        gs.ROOT = self.tmp / "不存在的目录"
        self.assertEqual(gs.scan(), [])

    def test_只收图片扩展名(self):
        files = gs.scan()
        self.assertEqual(len(files), 3, "txt 不该被当成表情包")
        self.assertTrue(all(f.lower().endswith(gs.EXT) for f in files))

    def test_按分类名命中(self):
        hit = gs.scan("晚安")
        self.assertEqual(len(hit), 1)
        self.assertIn("晚安喵.gif", hit[0])

    def test_按文件名关键词命中(self):
        hit = gs.scan("爱心")
        self.assertEqual(len(hit), 1, "标签写进文件名后应能按语义检索到")
        self.assertIn("偷来的", hit[0])

    def test_无命中时回退全库(self):
        hit = gs.scan("完全不存在的话题zzz")
        self.assertEqual(len(hit), 3, "没有命中就全库随机，宁可发一张也别不发")

    def test_整句话关键词能拆字匹配(self):
        hit = gs.scan("给我来一张开心的图")
        self.assertTrue(len(hit) >= 1)
        self.assertTrue(any("开心" in f for f in hit), "应优先命中含'开心'的图")

    def test_url_编码(self):
        f = str(self.tmp / "开心" / "哈哈大笑.png")
        url = gs.to_url(f)
        self.assertTrue(url.startswith("/img/"))
        self.assertNotIn("开心", url, "中文必须百分号编码，否则 NapCat 下载会 400")
        self.assertIn("%", url)


if __name__ == "__main__":
    unittest.main()
