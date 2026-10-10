# -*- coding: utf-8 -*-
r"""本地表情包图库服务。

为什么要它：外部表情包接口（api.lolimi.cn / fabiaoqing.com 的图床）已经全部失效，
而且随时可能再挂。改成读本地文件夹之后——零月费、不受外网影响、图库内容完全由你决定。

接口：
  GET  /health              健康检查
  GET  /list                每个分类当前有几张图
  GET  /random              全库随机一张，302 跳到图片
  GET  /random?kw=开心      按分类名或文件名关键词挑一张（无命中则全库随机）
  GET  /img/<分类>/<文件名>  图片本体
  GET  /stolen              自动收录统计（配合 sticker_collector）
  POST /collect             立刻扫描收录一次

目录约定（<仓库根>/表情包/）：
  开心/  无语/  疑惑/  安慰/  晚安/  打招呼/  随机/  偷来的/
  放 .png/.jpg/.gif/.webp 都行；文件名或所在文件夹名带关键词就能被挑中。
"""
import json
import os
import random
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

ROOT = paths.GALLERY_DIR
HOST = "127.0.0.1"
PORT = paths.gallery_port()
EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _name_of(path: str) -> str:
    """用于匹配的"名字"= 所在文件夹名 + 文件名（不含扩展名）。

    刻意不用完整路径：路径里的盘符、用户名、临时目录字符会造成误命中
    （曾经出现过关键词匹配到 C:\\Users\\<用户名> 里的字，挑出毫不相干的图）。
    """
    base = os.path.splitext(os.path.basename(path))[0]
    return (os.path.basename(os.path.dirname(path)) + " " + base).lower()


def _score(name: str, key: str):
    """给候选图打分：返回 (与关键词的最长公共子串长度, 命中的不同汉字个数)。

    为什么不用"单个字命中就算"：图库里有个文件夹叫「偷来的」，
    只要关键词里带"来"或"的"就会命中它，把真正该发的图挤掉。
    用最长公共子串做主指标，至少要有两个连续汉字对上才算命中。
    """
    best = 0
    n = len(name)
    for i in range(n):
        for j in range(i + 2, min(n, i + 10) + 1):
            if name[i:j] in key:
                best = j - i
                break
    chars = sum(1 for ch in set(key) if '一' <= ch <= '鿿' and ch in name)
    return best, chars


def scan(kw: str = ""):
    """收集候选图片。kw 命中分类目录名或文件名都算。"""
    files = []
    if not ROOT.is_dir():
        return files
    for dirpath, _dirs, names in os.walk(ROOT):
        for n in names:
            if n.lower().endswith(EXT):
                files.append(os.path.join(dirpath, n))
    if not files:
        return files
    key = (kw or "").strip().lower()
    if not key:
        return files

    # 1) 整串命中（分类名或文件名里包含完整关键词）
    hits = [f for f in files if key in _name_of(f)]
    if hits:
        return hits

    # 2) 模型经常传一整句话过来，按"最长公共子串"打分挑最贴的
    scored = sorted(((_score(_name_of(f), key), f) for f in files),
                    key=lambda x: x[0], reverse=True)
    if scored and scored[0][0][0] >= 2:
        top = scored[0][0]
        return [f for s, f in scored if s == top]

    # 3) 实在对不上就全库随机：宁可发一张不那么贴切的，也别不回图
    return files


def to_url(path: str) -> str:
    rel = os.path.relpath(path, str(ROOT)).replace("\\", "/")
    return "/img/" + urllib.parse.quote(rel)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _redirect(self, loc: str):
        self.send_response(302)
        self.send_header("Location", loc)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        kw = (qs.get("kw") or [""])[0]

        if parsed.path == "/health":
            return self._send(200, json.dumps({"ok": True, "root": str(ROOT)}, ensure_ascii=False).encode())

        if parsed.path == "/stolen":
            try:
                import sticker_collector
                return self._send(200, json.dumps(sticker_collector.summary(), ensure_ascii=False, indent=1).encode())
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False).encode())

        if parsed.path == "/list":
            stat = {}
            if ROOT.is_dir():
                for d in sorted(os.listdir(str(ROOT))):
                    p = ROOT / d
                    if p.is_dir():
                        stat[d] = len([n for n in os.listdir(str(p)) if n.lower().endswith(EXT)])
            return self._send(200, json.dumps(stat, ensure_ascii=False).encode())

        if parsed.path == "/random":
            pool = scan(kw)
            if not pool:
                return self._send(404, json.dumps(
                    {"error": "图库是空的。往 表情包/ 里放几张图，或先在 QQ 里发几张让它自动收录。"},
                    ensure_ascii=False).encode())
            return self._redirect(to_url(random.choice(pool)))

        if parsed.path.startswith("/img/"):
            rel = urllib.parse.unquote(parsed.path[len("/img/"):]).replace("/", os.sep)
            full = os.path.normpath(os.path.join(str(ROOT), rel))
            if not full.startswith(str(ROOT.resolve())) or not os.path.isfile(full):
                return self._send(404, b'{"error":"not found"}')
            with open(full, "rb") as f:
                data = f.read()
            ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}[
                os.path.splitext(full)[1].lower()]
            return self._send(200, data, ctype)

        return self._send(404, b'{"error":"no route"}')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/collect":
            try:
                import sticker_collector
                n = sticker_collector.scan_once()
                return self._send(200, json.dumps(
                    {"本轮新收录": n, "统计": sticker_collector.summary()}, ensure_ascii=False, indent=1).encode())
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False).encode())
        return self._send(404, b'{"error":"no route"}')

    def log_message(self, fmt, *args):
        pass


def main():
    paths.ensure_dirs()
    print("[图库] http://%s:%d  根目录 %s" % (HOST, PORT, ROOT))
    try:
        import sticker_collector
        sticker_collector.start()
    except Exception as e:
        print("[图库] 收录器启动失败（不影响发图）：%s" % e)
    try:
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    except OSError as e:
        print("[图库] 端口 %d 被占用或启动失败：%s" % (PORT, e))
        sys.exit(1)


if __name__ == "__main__":
    main()
