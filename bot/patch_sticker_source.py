# -*- coding: utf-8 -*-
"""把 api_collection 插件的表情包图源换成本地图库服务。

为什么需要打补丁：api_collection 的 random_emoji / sougou_image_search 原本调外部接口，
  * api.lolimi.cn —— 域名已不存在（三个公共 DNS 都是 NXDOMAIN）
  * fabiaoqing.com —— 能抓到直链，但图床 img.soutula.com 有防盗链，下载 403
外部图源这条路已经走不通，所以改成本地图库（127.0.0.1，零费用、不受外网影响）。

补丁是**幂等**的：重复运行不会重复修改；改之前会自动备份原文件。
如果哪天插件升级把补丁冲掉了，再跑一次本脚本即可（安装脚本和 一键启动 都会检查）。
"""
import re
import shutil
import sys
import time

import paths

MARKER = "本地表情包图库"

NEW_METHODS = '''    async def _fabiaoqing_image(self, keyword: str) -> str:
        r"""[patched by xiaomiao-qq-bot] 从本地表情包图库按关键词挑一张。

        原实现调外部接口（lolimi 已停服、fabiaoqing 图床 403），改为读本地图库服务。
        """
        import os as _os
        gallery = _os.environ.get("XIAOMIAO_GALLERY_URL", "%s")
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=8),
            ) as session:
                async with session.get(
                    gallery + "/random", params={"kw": keyword}, allow_redirects=True,
                ) as response:
                    if response.status == 404:
                        raise Exception("图库是空的：往 表情包/ 里放几张图，或先在 QQ 里发图让它自动收录")
                    response.raise_for_status()
                    final_url = str(response.url)
            if final_url.endswith("/random"):
                raise Exception("图库没返回图片")
            return final_url
        except aiohttp.ClientError:
            raise Exception("图库服务没启动，请双击 scripts\\\\启动图库.cmd")
        except Exception as e:
            if "图库" in str(e):
                raise
            raise Exception("获取表情包失败: %%s" %% e)

    async def get_random_emoji(self) -> str:
        """获取随机表情包图片链接（本地图库）"""
        return await self._fabiaoqing_image("随机")

    async def get_sougou_image(self, keyword: str) -> str:
        """按关键词从本地图库挑选表情包"""
        return await self._fabiaoqing_image(keyword)
''' % paths.gallery_url()


def find_target():
    sp = paths.site_packages()
    f = sp / "api_collection" / "api_collection.py"
    if not f.exists():
        sys.exit("没找到 %s\n请先安装插件：scripts\\安装.cmd 会自动装，"
                 "或手动 pip install chatgpt-mirai-qq-bot-api-collection" % f)
    return f


def patch(verbose=True):
    f = find_target()
    src = f.read_text(encoding="utf-8")
    if MARKER in src or "patched by xiaomiao-qq-bot" in src:
        if verbose:
            print("  [跳过] 图源已经是本地图库了")
        return False

    start = src.find("    async def _fabiaoqing_image")
    if start == -1:
        # 老版本可能没有这个函数，退化成替换两个 getter
        start = src.find("    async def get_random_emoji")
    if start == -1:
        sys.exit("插件结构和预期不一致，找不到要打补丁的函数。请提 issue 并附上插件版本。")

    m = re.search(r"\n    async def (?!_fabiaoqing_image|get_random_emoji|get_sougou_image)", src[start:])
    end = start + m.start() + 1 if m else len(src)

    backup = f.with_suffix(".py.orig-" + time.strftime("%Y%m%d%H%M%S"))
    shutil.copy2(str(f), str(backup))
    f.write_text(src[:start] + NEW_METHODS + src[end:], encoding="utf-8")
    if verbose:
        print("  [补丁] 图源已改为本地图库 %s" % paths.gallery_url())
        print("         原文件备份：%s" % backup.name)
    return True


if __name__ == "__main__":
    print("=" * 58)
    print("  表情包图源补丁")
    print("=" * 58)
    patch()
    # 语法自检：补丁写坏了要立刻发现，而不是等运行时炸
    import py_compile
    try:
        py_compile.compile(str(find_target()), doraise=True)
        print("  [自检] 补丁后的文件语法正常")
    except Exception as e:
        print("  [自检] 失败：%s" % e)
        sys.exit(1)
