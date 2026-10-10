# -*- coding: utf-8 -*-
r"""表情包自动收录器（俗称"偷表情"）。

原理：kirara 会把机器人**收到的每一张图**存进
    <kirara>/data/media/files/<sha1>.<ext>
并在 <kirara>/data/media/metadata/<sha1>.json 里记下来源
（source=im_message、references=["memory:group:<QQ号>"]）。

所以这里完全不用改 kirara 一行代码，纯旁路：
  1. 定时扫 metadata，把收到的图片复制进 表情包/偷来的/
  2. 用视觉模型给每张图打标签（情绪 + 关键词），写进文件名
     —— 之后图库按关键词挑图就能命中，形成"越聊越会斗图"的闭环
  3. 按 media_id（内容 sha1）去重，同一张图永远只收一次

两个必须知道的坑（都已处理）：
  * 机器人**自己发出去**的图，metadata 里 source 同样是 im_message，
    光看这个字段会把自己发的表情又偷回来。所以要再加两道过滤：
    references 为空的一律跳过；内容 sha1 已在图库里的一律跳过。
  * 别人发的照片、截图不是表情包，用体积上限挡掉（默认 1.5MB）。
"""
import base64
import hashlib
import json
import os
import re
import threading
import time
import urllib.request

import paths

GALLERY = paths.GALLERY_DIR
STOLEN = GALLERY / "偷来的"
INDEX = STOLEN / ".index.json"
MEDIA_DIR = paths.kirara_data_dir() / "media"

SCAN_INTERVAL = 20          # 秒
TAG_PER_CYCLE = 3           # 每轮最多打几个标签，避免瞬时刷爆 API
MAX_BYTES = 1_500_000       # 超过这个体积的多半是照片/截图，不当表情包
IMG_EXT = (".gif", ".png", ".jpg", ".jpeg", ".webp")
VISION_MODEL = "deepseek-v4-flash-vision-exp"

_lock = threading.Lock()
_stats = {"scans": 0, "stolen": 0, "tagged": 0, "skipped_big": 0, "errors": 0, "last_scan": None}


def _log(*a):
    print("[收录]", *a, flush=True)


def _deepseek():
    """从 kirara 配置里取 DeepSeek key/base（只在内存里用，不打印不落盘）。"""
    cfg = paths.kirara_data_dir() / "config.yaml"
    if not cfg.exists():
        return None, None
    txt = cfg.read_text(encoding="utf-8")
    key = re.search(r"api_key:\s*(\S+)", txt)
    base = re.search(r"api_base:\s*(\S+)", txt)
    return (key.group(1) if key else None), (base.group(1).rstrip("/") if base else None)


def _load_index():
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_index(idx):
    STOLEN.mkdir(parents=True, exist_ok=True)
    tmp = str(INDEX) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    os.replace(tmp, str(INDEX))


def _safe(s, limit=12):
    return re.sub(r"[^\w\u4e00-\u9fff]", "", s or "")[:limit]


def vision_tag(path):
    """让视觉模型给出「情绪|关键词1,关键词2」。失败返回 None，不影响收录。

    注意 max_tokens 要给够：这是思考模型，给太小（比如 40）会导致正文为空、
    内容全在 reasoning_content 里。
    """
    key, base = _deepseek()
    if not key or not base:
        return None
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = {"jpg": "jpeg"}.get(ext, ext)
    try:
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
    except Exception:
        return None
    body = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/%s;base64,%s" % (mime, b64)}},
            {"type": "text", "text": "这是一张聊天表情包。只输出一行，格式：情绪|关键词1,关键词2\n"
                                     "情绪不超过6个字，关键词用于日后按语义检索，不要解释，不要输出其它内容。"}]}],
        "max_tokens": 700,
    }
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
                                headers={"Content-Type": "application/json",
                                         "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        _log("打标失败:", type(e).__name__, str(e)[:80])
        return None
    m = d["choices"][0]["message"]
    txt = (m.get("content") or "").strip() or (m.get("reasoning_content") or "")
    hit = re.search(r"([\w\u4e00-\u9fff]{1,8})\s*[|｜]\s*([\w\u4e00-\u9fff,，、\s]{1,30})", txt)
    if not hit:
        return None
    kws = [_safe(k, 8) for k in re.split(r"[,，、]", hit.group(2)) if _safe(k, 8)][:2]
    return {"mood": _safe(hit.group(1), 8), "keywords": kws,
            "raw": txt[:120], "tokens": d.get("usage", {}).get("total_tokens")}


def _gallery_hashes():
    """图库里已有图片的内容 sha1 集合，用来识别"这图本来就是我们发出去的"。"""
    hs = set()
    for dirpath, _d, names in os.walk(str(GALLERY)):
        for n in names:
            if n.lower().endswith(IMG_EXT):
                try:
                    with open(os.path.join(dirpath, n), "rb") as fh:
                        hs.add(hashlib.sha1(fh.read()).hexdigest())
                except Exception:
                    pass
    return hs


def scan_once(do_tag=True):
    """扫一遍 media 元数据，收录新图片。返回本轮新收录数量。"""
    meta_dir = MEDIA_DIR / "metadata"
    file_dir = MEDIA_DIR / "files"
    if not meta_dir.is_dir():
        return 0
    STOLEN.mkdir(parents=True, exist_ok=True)
    with _lock:
        idx = _load_index()
        own = _gallery_hashes()
        pending = []
        for name in sorted(os.listdir(str(meta_dir))):
            if not name.endswith(".json"):
                continue
            mid = name[:-5]
            if mid in idx:
                continue
            try:
                meta = json.loads((meta_dir / name).read_text(encoding="utf-8"))
            except Exception:
                continue
            if meta.get("source") != "im_message" or meta.get("media_type") != "image":
                idx[mid] = {"skip": "非收到的图片", "at": time.strftime("%F %T")}
                continue
            if mid in own:
                idx[mid] = {"skip": "本来就是我们图库发出去的图", "at": time.strftime("%F %T")}
                continue
            refs = meta.get("references") or []
            if not refs:
                idx[mid] = {"skip": "无会话来源（疑似机器人自己发出）", "at": time.strftime("%F %T")}
                continue
            src = file_dir / (mid + "." + str(meta.get("format") or "png"))
            if not src.is_file():
                continue
            size = src.stat().st_size
            if size > MAX_BYTES:
                idx[mid] = {"skip": "超过体积上限（可能是照片/截图）", "size": size,
                            "at": time.strftime("%F %T")}
                _stats["skipped_big"] += 1
                continue
            ext = ("." + str(meta.get("format") or "png").lower())
            if ext not in IMG_EXT:
                idx[mid] = {"skip": "格式不收 " + ext, "at": time.strftime("%F %T")}
                continue
            idx[mid] = {
                "at": time.strftime("%F %T"),
                "created_at": meta.get("created_at"),
                "from": refs[0].replace("memory:", ""),
                "size": size, "format": meta.get("format"), "tag": None,
            }
            pending.append((mid, str(src), ext, idx[mid]))

        tagged = 0
        for mid, src, ext, rec in pending:
            tag = None
            if do_tag and tagged < TAG_PER_CYCLE:
                tag = vision_tag(src)
                tagged += 1
                if tag:
                    _stats["tagged"] += 1
            mood = _safe((tag or {}).get("mood") or "未打标", 8)
            kw = "_".join((tag or {}).get("keywords") or [])[:20]
            stem = "%s_%s_%s%s" % (time.strftime("%Y%m%d"), mid[:8], mood, ("_" + kw) if kw else "")
            dst_name = re.sub(r"[^\w\u4e00-\u9fff.\-]", "", stem) + ext
            dst = STOLEN / dst_name
            n = 1
            while dst.exists():
                dst = STOLEN / (dst_name[:-len(ext)] + "_%d%s" % (n, ext))
                n += 1
            try:
                with open(src, "rb") as fh:
                    dst.write_bytes(fh.read())
            except Exception as e:
                _log("复制失败", e)
                _stats["errors"] += 1
                idx.pop(mid, None)
                continue
            rec["file"] = dst.name
            rec["tag"] = tag
            _stats["stolen"] += 1
            _log("收录 %s <- %s (%d KB)%s" % (dst.name, rec["from"], rec["size"] // 1024,
                                             " 标签:" + mood if tag else ""))

        # 上一轮没打上标签的，这轮补
        for mid, rec in idx.items():
            if isinstance(rec, dict) and rec.get("file") and not rec.get("tag") and do_tag \
                    and tagged < TAG_PER_CYCLE * 2:
                p = STOLEN / rec["file"]
                if p.is_file():
                    t = vision_tag(str(p))
                    if t:
                        rec["tag"] = t
                        tagged += 1
                        _stats["tagged"] += 1
                        _log("补标签 %s -> %s" % (rec["file"], t.get("mood")))

        _save_index(idx)
        _stats["scans"] += 1
        _stats["last_scan"] = time.strftime("%F %T")
        return len(pending)


def summary():
    with _lock:
        idx = _load_index()
    kept = {k: v for k, v in idx.items() if isinstance(v, dict) and v.get("file")}
    by_conv = {}
    for v in kept.values():
        by_conv[v.get("from", "?")] = by_conv.get(v.get("from", "?"), 0) + 1
    recent = sorted(kept.values(), key=lambda x: x.get("at") or "", reverse=True)[:10]
    return {
        "已收录": len(kept),
        "已打标": sum(1 for v in kept.values() if v.get("tag")),
        "按来源": by_conv,
        "跳过大图": _stats["skipped_big"],
        "扫描次数": _stats["scans"],
        "最后扫描": _stats["last_scan"],
        "目录": str(STOLEN),
        "最近": [{"文件": v.get("file"), "来源": v.get("from"), "时间": v.get("at"),
                 "标签": (v.get("tag") or {}).get("mood")} for v in recent],
    }


def _loop():
    while True:
        try:
            scan_once()
        except Exception as e:
            _stats["errors"] += 1
            _log("扫描异常:", type(e).__name__, str(e)[:120])
        time.sleep(SCAN_INTERVAL)


def start():
    STOLEN.mkdir(parents=True, exist_ok=True)
    t = threading.Thread(target=_loop, daemon=True, name="sticker-collector")
    t.start()
    _log("收录器已启动，每 %d 秒扫一次 %s" % (SCAN_INTERVAL, MEDIA_DIR))
    return t
