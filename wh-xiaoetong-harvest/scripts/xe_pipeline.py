#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xe_pipeline.py — 小鹅通课程批量下载与整理流水线

从 xe_server.py 落盘的 state.json 读取采集清单，串起四个阶段：
    download   m3u8 改写（KEY URI 指向本地解密密钥）+ ffmpeg 拉流解密合并为 mp4 + ffprobe 验证
    organize   建立课程根文件夹：章节子文件夹 / 课时子文件夹，每节同时含 md 与 mp4
    obsidian   先归档再同步到 Obsidian 仓库（默认 ~/Documents/Xiaoetong）
    transcribe 可选：调用捆绑的 xiaoetong_transcript.py（faster-whisper GPU）生成逐字稿回填 md

用法：
    python xe_pipeline.py --workdir <采集工作目录> --stage all
    python xe_pipeline.py --workdir <workdir> --stage download --course-id course_xxx
    python xe_pipeline.py --workdir <workdir> --stage organize --root-name "你的课程名"
    python xe_pipeline.py --workdir <workdir> --stage obsidian --dry-run

命名铁律：文件名一律取采集清单里的真实标题（目录页显示名），推断名必须带【待核对】。
"""
import argparse
import base64
import functools
import json
import re
import concurrent.futures
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
DEFAULT_VAULT = str(Path.home() / "Documents/Xiaoetong")
DEFAULT_ARCHIVE = str(Path.home() / "Documents/Xiaoetong-archive")
KEY_URI_RE = re.compile(r'URI="([^"]*)"')


def log(msg: str):
    print(f"[xe_pipeline] {msg}", flush=True)


def ffmpeg_bin() -> str:
    return "ffmpeg"


def ffprobe_bin() -> str:
    return "ffprobe"


def start_static_server(root: Path):
    """在 root 上起 127.0.0.1 随机端口静态服务，返回 (port, shutdown_fn)。

    ffmpeg 的 -headers/-user_agent 等 http 协议选项只对 http/https 输入有效；
    本地 file 输入会报 'Option not found'。因此 playlist 与 key.bin 经本服务
    以 http 输入喂给 ffmpeg，且头选项会透传给远端 ts 分段请求。"""
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return port, server.shutdown


def safe_title(title: str) -> str:
    """标题清洗为合法 Windows 文件名：去省略号/非法字符/首尾点空格，限长 80。"""
    t = (title or "").replace("…", "").replace("...", "").strip()
    t = re.sub(r'[\\/:*?"<>|\r\n\t]', "", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip(". ")
    return t[:80] if t else ""


def chapter_dir_name(chapter: str, title: str) -> str:
    """章节文件夹命名：优先采集到的章节名；否则从标题前缀序号推断（5-1xxx -> 第5章）；否则【正文】。"""
    c = safe_title(chapter)
    if c:
        return c
    m = re.match(r"^(\d{1,3})(?=[-\s.、章])", (title or "").strip())
    if m:
        return f"第{int(m.group(1))}章"
    return "正文"


def extract_cdn_id(m3u8_url: str, m3u8_text: str) -> str:
    """从 m3u8 来源 URL 或 ts 行提取 CDN 层视频 ID（防重复下载依据）。
    v-vod-k 形态：/video/b_u_xxx/{token}/drm/... 取 {token}（drm/main 等固定段排除）。"""
    if m3u8_url:
        m = re.search(r"/([0-9a-fA-F]{10,})vodcq", m3u8_url)
        if m:
            return m.group(1)
        m2 = re.search(r"/video/b_u_[^/]+/([^/]+)/drm/", m3u8_url)
        if m2 and m2.group(1) not in ("main", "drm"):
            return m2.group(1)
    for line in (m3u8_text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            m2 = re.search(r"/video/b_u_[^/]+/([^/]+)/drm/", line)
            if m2 and m2.group(1) not in ("main", "drm"):
                return m2.group(1)
            m3 = re.search(r"/([0-9a-fA-F]{10,})vodcq", line)
            if m3:
                return m3.group(1)
            break
    return ""


def extinf_total(m3u8_text: str) -> float:
    total = 0.0
    for line in m3u8_text.splitlines():
        if line.startswith("#EXTINF:"):
            try:
                total += float(line.split(":", 1)[1].split(",", 1)[0])
            except Exception:
                pass
    return total


def rewrite_playlist(text: str, key_name: str = "key.bin") -> str:
    """把远程 KEY URI 改写为本地相对路径（ffmpeg 直接读本地解密后的密钥文件）；
    丢弃 URI 为空的 KEY 行；绝对 ts 行若带重复 sign 参数（旧钩子重复拼 &param）
    则截断保留首段参数，否则 CDN 403。"""
    out_lines = []
    for line in text.splitlines():
        if line.startswith("#EXT-X-KEY"):
            if 'URI=""' in line:
                continue
            line = KEY_URI_RE.sub(f'URI="{key_name}"', line, count=1)
        elif line.startswith("http") and line.count("sign=") > 1:
            pos = line.find("sign=")
            pos2 = line.find("sign=", pos + 5)
            if pos2 > 0:
                line = line[:pos2 - 1]
        out_lines.append(line)
    return "\n".join(out_lines) + "\n"


def pyts_download(m3u8_text: str, dl_dir: Path, referer: str, ua: str, threads: int = 8):
    """urllib 逐分片下载（带 Referer/UA，绕过 ffmpeg 分段请求不带头的坑），
    生成本地 playlist（ts=本地绝对路径，key=key.bin 相对）供 ffmpeg 本地解密。"""
    seg_dir = dl_dir / "seg"
    seg_dir.mkdir(parents=True, exist_ok=True)
    segs = []
    has_key = False
    key_uri = ""
    iv_hex = ""
    for line in m3u8_text.splitlines():
        if line.startswith("#EXT-X-KEY"):
            has_key = True
            m4 = __import__("re").search(r'URI="([^"]*)"', line)
            if m4:
                key_uri = m4[1]
            m5 = __import__("re").search(r"IV=0x([0-9a-fA-F]{1,32})", line)
            if m5:
                iv_hex = m5.group(1)
        elif line and not line.startswith("#"):
            l2 = line
            if l2.startswith("http") and l2.count("sign=") > 1:
                pos = l2.find("sign=")
                pos2 = l2.find("sign=", pos + 5)
                if pos2 > 0:
                    l2 = l2[: pos2 - 1]
            segs.append(l2)
    if not segs:
        raise RuntimeError("m3u8 中没有可下载的 ts 分片")
    hdr = {"Referer": referer, "User-Agent": ua}

    def grab(i, url):
        out = seg_dir / f"seg_{i:05d}.ts"
        if out.exists() and out.stat().st_size > 0:
            return i, out
        last = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers=hdr)
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                if not data:
                    raise RuntimeError("empty body")
                out.write_bytes(data)
                return i, out
            except Exception as e:
                last = e
        raise RuntimeError(f"segment {i} failed: {last}")

    ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
        futs = {ex.submit(grab, i, u): i for i, u in enumerate(segs)}
        for f in concurrent.futures.as_completed(futs):
            _, _out = f.result()
            ok += 1
    # 解密 + 拼接：密钥 = 直取 KEY URI 响应字节（本课程无需 &uid/XOR，猫抓同款做法）；
    # IV 取 m3u8 显式值（如 0x00000000 -> 16 字节 0），无则按分片序号。
    merged = dl_dir / "all.ts"
    with merged.open("wb") as mout:
        if has_key:
            if not key_uri:
                raise RuntimeError("m3u8 带 KEY 但无 URI")
            try:
                from Crypto.Cipher import AES
            except Exception as exc:
                raise RuntimeError("需 pycryptodome：python -m pip install pycryptodome（venv 运行）: " + str(exc))
            req = urllib.request.Request(key_uri, headers=hdr)
            with urllib.request.urlopen(req, timeout=30) as r:
                key = r.read()
            (dl_dir / "key.bin").write_bytes(key)
            iv_fixed = bytes.fromhex(iv_hex.rjust(32, "0")) if iv_hex else None
            for i in range(len(segs)):
                data = (seg_dir / f"seg_{i:05d}.ts").read_bytes()
                iv = iv_fixed if iv_fixed is not None else (i).to_bytes(16, "big")
                dec = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
                pad = dec[-1]
                if 1 <= pad <= 16 and dec[-pad:] == bytes([pad]) * pad:
                    dec = dec[:-pad]
                mout.write(dec)
        else:
            for i in range(len(segs)):
                mout.write((seg_dir / f"seg_{i:05d}.ts").read_bytes())
    return None, ok


def load_state(workdir: Path) -> dict:
    state_path = workdir / "state.json"
    if not state_path.exists():
        raise SystemExit(f"[错误] 未找到 {state_path}，请先运行 xe_server.py 完成采集")
    return json.loads(state_path.read_text(encoding="utf-8"))


def save_state(workdir: Path, state: dict):
    tmp = workdir / "state.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(workdir / "state.json")


def ffprobe_info(mp4: Path) -> dict:
    try:
        r = subprocess.run(
            [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration,size",
             "-of", "default=noprint_wrappers=1", str(mp4)],
            capture_output=True, text=True, timeout=120,
        )
        info = {}
        for line in (r.stdout or "").splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                info[k.strip()] = v.strip()
        return info
    except Exception:
        return {}


def load_history(workdir: Path) -> dict:
    p = workdir / "history.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_history(workdir: Path, hist: dict):
    p = workdir / "history.json"
    tmp = p.with_name("history.json.tmp")
    tmp.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def pick_lessons(state: dict, args) -> list:
    lessons = list(state.get("lessons", {}).values())
    if args.course_id:
        lessons = [x for x in lessons if x.get("course_id") == args.course_id]
    if args.video_id:
        lessons = [x for x in lessons if x.get("video_id") == args.video_id]
    lessons.sort(key=lambda x: (x.get("course_id") or "", x.get("chapter") or "", x.get("title") or ""))
    if args.limit:
        lessons = lessons[: args.limit]
    return lessons


def referer_for(lesson: dict, override: str) -> str:
    if override:
        return override
    page = lesson.get("page_url") or ""
    if page:
        try:
            u = urlparse(page)
            if u.scheme and u.netloc:
                return f"{u.scheme}://{u.netloc}/"
        except Exception:
            pass
    return "https://APP_YOUR_ID.h5.xet.pomoho.com/"


def stage_download(args, workdir: Path, state: dict) -> int:
    raw_dir = workdir / "raw"
    dl_root = workdir / "dl"
    dl_root.mkdir(parents=True, exist_ok=True)
    hist = load_history(workdir)
    lessons = pick_lessons(state, args)
    if not lessons:
        log("清单中没有可处理的课时（检查 --course-id/--video-id 过滤条件）")
        return 0
    log(f"待处理 {len(lessons)} 节，引擎 {args.engine}")
    server_shutdown = None
    if args.engine == "ffmpeg":
        port, server_shutdown = start_static_server(dl_root)
        log(f"本地静态服务已启动 http://127.0.0.1:{port}（承载 playlist 与 key.bin）")
    fail = 0
    for lesson in lessons:
        vid = lesson.get("video_id") or ""
        title = lesson.get("title") or vid
        raw_m3u8 = raw_dir / f"{vid}.m3u8"
        if not raw_m3u8.exists():
            log(f"[skip] {vid} 《{title}》 无 m3u8 采集记录")
            continue
        m3u8_text = raw_m3u8.read_text(encoding="utf-8")

        # 防重复（下载层）：history 以 video_id 为主键，CDN id 为副键
        if vid in hist and (Path(hist[vid].get("mp4", "")).exists()):
            lesson["status"] = "downloaded"
            lesson["mp4"] = hist[vid]["mp4"]
            log(f"[skip] {vid} 《{title}》 已在历史记录中（{hist[vid].get('at', '')}）")
            continue
        cdn_id = extract_cdn_id(lesson.get("m3u8_url") or "", m3u8_text)
        if cdn_id and cdn_id in hist and Path(hist[cdn_id].get("mp4", "")).exists():
            log(f"[block] {vid} 《{title}》 CDN video ID {cdn_id} 已下载过（同视频新签名），拒绝重复下载")
            lesson["status"] = "duplicate"
            continue

        dl_dir = dl_root / vid
        dl_dir.mkdir(parents=True, exist_ok=True)
        has_key = "#EXT-X-KEY" in m3u8_text
        key_b64 = lesson.get("key_b64") or ""
        if has_key and not key_b64:
            log(f"[wait] {vid} 《{title}》 m3u8 带 AES-128 密钥但密钥未采集到，暂不能下载")
            lesson["status"] = "key_missing"
            fail += 1
            continue
        if key_b64:
            (dl_dir / "key.bin").write_bytes(base64.b64decode(key_b64))
        playlist = dl_dir / "playlist.m3u8"
        playlist.write_text(rewrite_playlist(m3u8_text), encoding="utf-8")

        out_mp4 = dl_dir / f"{vid}.mp4"
        referer = referer_for(lesson, args.referer)
        log(f"[download] {vid} 《{title}》 分片 {sum(1 for l in m3u8_text.splitlines() if l and not l.startswith('#'))} 密钥={'Y' if key_b64 else 'N'}")
        if args.engine == "nre":
            if not args.nre_bin:
                log("[错误] --engine nre 需要 --nre-bin 指向 N_m3u8DL-RE.exe")
                fail += 1
                continue
            cmd = [args.nre_bin, str(playlist), "--save-dir", str(dl_dir),
                   "-H", f"Referer: {referer}", "-H", f"User-Agent: {args.ua}", "--thread-count", "16"]
        elif args.engine == "pyts":
            try:
                playlist_local, ok_seg = pyts_download(m3u8_text, dl_dir, referer_for(lesson, args.referer), args.ua)
                log(f"[pyts] {vid} 分段下载 {ok_seg}/{sum(1 for l in m3u8_text.splitlines() if l and not l.startswith('#'))}")
            except Exception as e:
                log(f"[fail] {vid} 《{title}》 pyts 分段下载失败: {e}")
                lesson["status"] = "download_failed"
                fail += 1
                continue
            feed_ts = dl_dir / "all.ts"
            if not feed_ts.exists():
                raise RuntimeError("pyts 未生成 all.ts")
            cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "warning", "-stats",
                   "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                   "-i", str(feed_ts),
                   "-map", "0", "-c", "copy", "-bsf:a", "aac_adtstoasc",
                   str(out_mp4)]
        else:
            # 注意：-headers 仅对 http/https 输入有效；本地 playlist 输入会报
            # "Option headers not found"。真实 CDN 带 sign 参数通常不校验 Referer
            # （猫抓无 Referer 下载已验证成功）；确需 Referer 的场景改用 NRE 引擎。
            hdr = f"Referer: {referer}\r\nUser-Agent: {args.ua}\r\n"
            feed = f"http://127.0.0.1:{port}/{vid}/playlist.m3u8"
            cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "warning", "-stats",
                   "-allowed_extensions", "ALL",
                   "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                   "-headers", hdr,
                   "-user_agent", args.ua,
                   "-i", feed,
                   "-map", "0", "-c", "copy", "-bsf:a", "aac_adtstoasc",
                   str(out_mp4)]
        with open(dl_dir / "tool.log", "w", encoding="utf-8", errors="replace") as lf:
            r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(dl_dir))
        if r.returncode != 0 or not out_mp4.exists():
            tail = ""
            try:
                tail = (dl_dir / "tool.log").read_text(encoding="utf-8", errors="replace")[-800:]
            except Exception:
                pass
            log(f"[fail] {vid} 《{title}》 下载失败 exit={r.returncode}，日志 {dl_dir / 'tool.log'} 末尾:\n{tail}")
            lesson["status"] = "download_failed"
            fail += 1
            continue

        info = ffprobe_info(out_mp4)
        expect = extinf_total(m3u8_text)
        dur = float(info.get("duration") or 0)
        size = int(float(info.get("size") or 0))
        if dur <= 0 or size <= 0:
            log(f"[fail] {vid} 《{title}》 ffprobe 验证失败 duration={dur} size={size}")
            lesson["status"] = "download_failed"
            fail += 1
            continue
        if expect > 0 and abs(dur - expect) / expect > 0.05:
            log(f"[warn] {vid} 《{title}》 时长偏差超 5%: ffprobe={dur:.0f}s EXTINF合计={expect:.0f}s")
        lesson.update({
            "status": "downloaded",
            "mp4": str(out_mp4),
            "duration_seconds": round(dur, 1),
            "size_bytes": size,
            "cdn_id": cdn_id,
            "downloaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        hist[vid] = {"mp4": str(out_mp4), "size": size, "cdn_id": cdn_id, "at": lesson["downloaded_at"]}
        if cdn_id:
            hist[cdn_id] = hist[vid]
        save_state(workdir, state)
    save_state(workdir, state)
    if server_shutdown is not None:
        try:
            server_shutdown()
        except Exception:
            pass
    return fail


def resolve_root_name(args, state: dict, lessons: list) -> str:
    if args.root_name:
        return safe_title(args.root_name)
    for lesson in lessons:
        if lesson.get("course_title"):
            return safe_title(lesson["course_title"])
    for course in state.get("courses", {}).values():
        if course.get("course_title"):
            return safe_title(course["course_title"])
    for lesson in lessons:
        if lesson.get("course_id"):
            return lesson["course_id"]
    return "小鹅通课程"


def write_lesson_md(lesson: dict, lesson_dir: Path, md_path: Path, transcript_dir: Path):
    vid = lesson.get("video_id") or ""
    title = safe_title(lesson.get("title") or vid)
    transcript_md = transcript_dir / f"{vid}.md"
    transcript_body = ""
    status = "待转写"
    if transcript_md.exists():
        raw = transcript_md.read_text(encoding="utf-8")
        if "## 逐字稿" in raw:
            transcript_body = raw.split("## 逐字稿", 1)[1].strip()
            status = "已转写"
        elif raw.strip():
            transcript_body = raw.strip()
            status = "已转写"
    if not transcript_body:
        transcript_body = "【待转写】本节逐字稿尚未生成。运行 transcribe 阶段（faster-whisper large-v3 GPU）后此节自动回填段落级时间戳逐字稿。"
    lines = [
        "---",
        f"course: {lesson.get('course_title') or ''}",
        f"chapter: {lesson.get('chapter') or chapter_dir_name(lesson.get('chapter', ''), title)}",
        f"title: {lesson.get('title') or ''}",
        f"video_id: {vid}",
        f"source: {lesson.get('page_url') or ''}",
        f"captured_at: {lesson.get('captured_at') or ''}",
        f"downloaded_at: {lesson.get('downloaded_at') or ''}",
        f"duration_seconds: {lesson.get('duration_seconds', '')}",
        f"size_bytes: {lesson.get('size_bytes', '')}",
        f"status: {status}",
        "---",
        "",
        f"# {title}",
        "",
        f"> 所属课程：{lesson.get('course_title') or ''}",
        f"> 章节：{lesson.get('chapter') or chapter_dir_name(lesson.get('chapter', ''), title)}",
        f"> 视频文件：[{title}.mp4]({title}.mp4)（与本文档同目录）",
        "",
        "## 逐字稿",
        "",
        transcript_body,
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return status


def stage_organize(args, workdir: Path, state: dict) -> int:
    lessons = [x for x in pick_lessons(state, args) if x.get("status") == "downloaded" and x.get("mp4")]
    if not lessons:
        log("没有已下载（downloaded）的课时可整理，先运行 --stage download")
        return 0
    root_name = resolve_root_name(args, state, lessons)
    root = Path(args.out_root) / root_name
    transcript_dir = workdir / "transcripts"
    if args.dry_run:
        log(f"[dry-run] 将创建 {root}，共 {len(lessons)} 节")
        for lesson in lessons:
            ch = chapter_dir_name(lesson.get("chapter", ""), lesson.get("title", ""))
            t = safe_title(lesson.get("title") or lesson["video_id"])
            log(f"[dry-run]   {ch}/{t}/{t}.mp4 + {t}.md")
        return 0
    root.mkdir(parents=True, exist_ok=True)
    counts = {"md": 0, "mp4": 0}
    for lesson in lessons:
        t = safe_title(lesson.get("title") or lesson["video_id"])
        if not t:
            t = lesson["video_id"]
        ch = chapter_dir_name(lesson.get("chapter", ""), t)
        chapter_dir = root / ch
        lesson_dir = chapter_dir / t
        n = 2
        while lesson_dir.exists() and lesson_dir.is_dir():
            mp4_target = lesson_dir / f"{t}.mp4"
            src_mp4 = Path(lesson["mp4"])
            if mp4_target.exists() and mp4_target.stat().st_size == src_mp4.stat().st_size:
                break  # 同内容重复运行：幂等跳过
            lesson_dir = chapter_dir / f"{t} -{n}"
            n += 1
        lesson_dir.mkdir(parents=True, exist_ok=True)
        src_mp4 = Path(lesson["mp4"])
        dst_mp4 = lesson_dir / f"{t}.mp4"
        if not dst_mp4.exists() or dst_mp4.stat().st_size != src_mp4.stat().st_size:
            shutil.copy2(str(src_mp4), str(dst_mp4))
        status = write_lesson_md(lesson, lesson_dir, lesson_dir / f"{t}.md", transcript_dir)
        counts["md"] += 1
        counts["mp4"] += 1
        log(f"[organize] {ch}/{t} ({status})")
    index_path = root / f"{root_name}.md"
    by_chapter = {}
    for lesson in lessons:
        ch = chapter_dir_name(lesson.get("chapter", ""), lesson.get("title", ""))
        by_chapter.setdefault(ch, []).append(lesson)
    idx = [
        f"# {root_name}",
        "",
        f"> 来源：小鹅通课程 ｜ 由 wh-xiaoetong-harvest 生成于 {time.strftime('%Y-%m-%d %H:%M')}",
        f"> 共 {len(lessons)} 节，每节子文件夹内含逐字稿 md 与视频 mp4",
        "",
    ]
    for ch in sorted(by_chapter):
        idx.append(f"## {ch}")
        idx.append("")
        for lesson in sorted(by_chapter[ch], key=lambda x: x.get("title") or ""):
            t = safe_title(lesson.get("title") or lesson["video_id"])
            idx.append(f"- [{t}](./{ch}/{t}/{t}.md)")
        idx.append("")
    index_path.write_text("\n".join(idx), encoding="utf-8")
    log(f"[done] 整理完成：{root}（{counts['md']} md / {counts['mp4']} mp4，索引 {index_path.name}）")
    return 0


def stage_obsidian(args, workdir: Path, state: dict) -> int:
    lessons = [x for x in pick_lessons(state, args) if x.get("status") == "downloaded"]
    root_name = resolve_root_name(args, state, lessons)
    src = Path(args.out_root) / root_name
    if not src.is_dir():
        log(f"[错误] 未找到已整理目录 {src}，先运行 --stage organize")
        return 1
    vault = Path(args.obsidian_vault)
    if not vault.is_dir():
        log(f"[错误] Obsidian 目录不存在：{vault}")
        return 1
    target = vault / root_name
    log(f"[obsidian] 源 {src}")
    log(f"[obsidian] 目标 {target}")
    if args.dry_run:
        if target.exists():
            log(f"[dry-run] 目标已存在，将先归档到 {Path(args.archive_root)}")
        log("[dry-run] 将复制目录树并校验文件数")
        return 0
    if target.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = Path(args.archive_root) / f"{stamp}-xiaoe-harvest-obsidian" / root_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(dest))
        log(f"[archive] 旧版已归档 -> {dest}")
    shutil.copytree(str(src), str(target))
    src_md = sum(1 for p in src.rglob("*.md"))
    src_mp4 = sum(1 for p in src.rglob("*.mp4"))
    dst_md = sum(1 for p in target.rglob("*.md"))
    dst_mp4 = sum(1 for p in target.rglob("*.mp4"))
    log(f"[verify] md {dst_md}/{src_md}  mp4 {dst_mp4}/{src_mp4}")
    if (src_md, src_mp4) != (dst_md, dst_mp4):
        log("[fail] 同步后文件数不一致，请检查")
        return 1
    log(f"[done] Obsidian 同步完成：{target}")
    return 0


def stage_transcribe(args, workdir: Path, state: dict) -> int:
    script = Path(__file__).resolve().parent / "xiaoetong_transcript.py"
    if not script.exists():
        log(f"[错误] 未找到转写脚本 {script}")
        return 1
    transcript_dir = workdir / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    lessons = [x for x in pick_lessons(state, args) if x.get("status") == "downloaded" and x.get("mp4")]
    done = 0
    for lesson in lessons:
        vid = lesson["video_id"]
        out_md = transcript_dir / f"{vid}.md"
        if out_md.exists() and not args.force:
            continue
        log(f"[transcribe] {vid} 《{lesson.get('title')}》 model={args.model}")
        r = subprocess.run([sys.executable, str(script), lesson["mp4"],
                            "--model", args.model, "--out", str(out_md)])
        if r.returncode != 0 or not out_md.exists():
            log(f"[fail] {vid} 转写失败（GPU 未就绪先跑 xe_doctor.py / verify_env）")
            continue
        done += 1
        save_state(workdir, state)
    log(f"[done] 本轮转写 {done} 节；随后运行 --stage organize --stage obsidian 回填 md")
    return 0


def main():
    ap = argparse.ArgumentParser(description="小鹅通课程批量下载与整理流水线")
    ap.add_argument("--workdir", required=True, help="采集工作目录（xe_server.py 的 --workdir）")
    ap.add_argument("--stage", default="all", choices=["all", "download", "organize", "obsidian", "transcribe"])
    ap.add_argument("--root-name", default="", help="课程根文件夹名（默认取采集到的课程真实标题）")
    ap.add_argument("--out-root", default=None, help="整理输出根目录（默认 workdir/organized）")
    ap.add_argument("--obsidian-vault", default=DEFAULT_VAULT, help="Obsidian 目标目录")
    ap.add_argument("--archive-root", default=DEFAULT_ARCHIVE, help="归档根目录（先归档再修改）")
    ap.add_argument("--engine", default="ffmpeg", choices=["ffmpeg", "nre", "pyts"])
    ap.add_argument("--nre-bin", default="", help="N_m3u8DL-RE.exe 路径（--engine nre 时必填）")
    ap.add_argument("--referer", default="", help="覆盖防盗链 Referer（默认取课时 page_url 源站）")
    ap.add_argument("--ua", default=DEFAULT_UA)
    ap.add_argument("--course-id", default="", help="只处理指定课程")
    ap.add_argument("--video-id", default="", help="只处理指定课时")
    ap.add_argument("--limit", type=int, default=0, help="本轮最多处理 N 节（0=全部）")
    ap.add_argument("--model", default="large-v3", help="转写模型（transcribe 阶段）")
    ap.add_argument("--force", action="store_true", help="transcribe 阶段强制重转")
    ap.add_argument("--dry-run", action="store_true", help="organize/obsidian 只打印计划不落盘")
    args = ap.parse_args()
    workdir = Path(args.workdir).resolve()
    if not args.out_root:
        args.out_root = str(workdir / "organized")
    state = load_state(workdir)
    rc = 0
    if args.stage in ("all", "download"):
        rc |= stage_download(args, workdir, state)
    if args.stage in ("all", "organize"):
        rc |= stage_organize(args, workdir, state)
    if args.stage in ("all", "obsidian"):
        rc |= stage_obsidian(args, workdir, state)
    if args.stage == "transcribe":
        rc |= stage_transcribe(args, workdir, state)
    sys.exit(0 if rc == 0 else 2)


if __name__ == "__main__":
    main()
