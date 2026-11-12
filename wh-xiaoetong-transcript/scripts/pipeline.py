"""
wh-xiaoetong-transcript 流水线编排器
=====================================
把【猫抓 m3u8 -> 桌面简体逐字稿】的完整链路串成一条命令。

两个主模式:
    A) 从 m3u8 下载+转写:   python pipeline.py --m3u8 "<URL>" [--title "真实标题"]
    B) mp4 直接转写:        python pipeline.py --mp4 "./path/视频.mp4" [--title "真实标题"]
一个收尾模式:
    C) 命名+交付(标题后补):  python pipeline.py --finalize --tmp "transcripts/.tmp.md"
                           --mp4 "downloads/_tmp/xxx.mp4" --title "真实标题"

无 --title 时下载+转写后停在 .tmp，输出提示由 AI 读内容推断命名，再走 finalize。
防重复: 维护 downloads/.history.json 记录 video_id，同视频拒绝重复下载。

依赖: 工作区资产 (N_m3u8DL-RE / xiaoetong_transcript.py) 见 references/download-recipes.md
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------- 路径常量 ----------
WS = Path.home() / "Documents/Xiaoetong-Transcript"
DOWNLOADS = WS / "downloads"
TRANSCRIPTS = WS / "transcripts"
HISTORY = DOWNLOADS / ".history.json"
N_M3U8DL = WS / "downloader/N_m3u8DL-RE/N_m3u8DL-RE.exe"
TRANSCRIPT_PY = Path(__file__).resolve().parent / "xiaoetong_transcript.py"
DESKTOP = Path.home() / "Desktop"
REFERER = os.environ.get("XIAOETONG_REFERER", "")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


# ---------- 工具函数 ----------
def log(msg: str):
    print(f"[pipeline] {msg}", flush=True)


def load_history() -> dict:
    if HISTORY.exists():
        try:
            return json.loads(HISTORY.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_history(h: dict):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_video_id(m3u8_url: str) -> str:
    """提取真正的视频 ID（URL 路径第二段）。

    小鹅通 m3u8 URL 结构:
      https://{host}/{account_id}vodcq{cid}/{video_id}/playlist_eof.m3u8
    第一段 {account_id}vodcq 是所有视频共享的账户/空间 ID（如 522ff1e0），
    第二段 {video_id} 才是视频唯一标识（如 46c4c8615001834818269116247）。
    playlist 文件名是最后一段，所以取倒数第二段。
    """
    from urllib.parse import urlparse
    parts = [p for p in urlparse(m3u8_url).path.split("/") if p]
    return parts[-2] if len(parts) >= 2 else ""


def check_duplicate(video_id: str) -> tuple:
    """返回 (是否重复, 已有记录 dict 或 None)。重复=同视频新签名。"""
    h = load_history()
    if video_id and video_id in h:
        return True, h[video_id]
    return False, None


def run(cmd: list, **kw):
    log("执行: " + " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, **kw)


def download_m3u8(m3u8_url: str, video_id: str) -> Path:
    """N_m3u8DL-RE 下载到 downloads/_tmp_{vid}，返回产物 mp4 路径。"""
    if not REFERER:
        raise SystemExit("请先设置 XIAOETONG_REFERER 为课程播放页的站点地址")
    tmpdir = DOWNLOADS / f"_tmp_{video_id or int(time.time())}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    r = run([
        str(N_M3U8DL),
        m3u8_url,
        "--save-dir", str(tmpdir),
        "-H", f"Referer: {REFERER}",
        "-H", f"User-Agent: {UA}",
        "--thread-count", "16",
    ])
    if r.returncode != 0:
        raise SystemExit(f"[错误] 下载失败 (exit {r.returncode})，见上方日志")
    mp4s = sorted(tmpdir.glob("*.mp4"))
    if not mp4s:
        raise SystemExit(f"[错误] 未找到下载产物 mp4: {tmpdir}")
    return mp4s[0]


def verify_video(mp4: Path) -> dict:
    """ffprobe 验证，返回 {duration, size}。"""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-of", "default=noprint_wrappers=1", str(mp4)],
        capture_output=True, text=True,
    )
    info = {"duration": "", "size": ""}
    for line in (r.stdout or "").splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            info[k.strip()] = v.strip()
    return info


def transcribe(mp4: Path, model: str) -> Path:
    """转写到 transcripts/.tmp-{stamp}.md，返回输出路径。"""
    out = TRANSCRIPTS / f".tmp-{int(time.time())}.md"
    r = run([
        sys.executable, str(TRANSCRIPT_PY), str(mp4),
        "--model", model, "--out", str(out),
    ])
    if r.returncode != 0:
        raise SystemExit(f"[错误] 转写失败 (exit {r.returncode})")
    if not out.exists():
        raise SystemExit("[错误] 转写未生成输出文件")
    return out


def safe_title(title: str) -> str:
    """清洗标题为合法文件名（去非法字符/省略号）。"""
    title = title.replace("…", "").replace("...", "").strip()
    title = re.sub(r'[\\/:*?"<>|]', "", title).strip()
    return title


def finalize(tmp_md: Path, mp4: Path, title: str, video_id: str):
    """命名 + 三位置交付（downloads/transcripts/桌面）。"""
    t = safe_title(title)
    if not t:
        raise SystemExit("[错误] 标题为空，无法命名")

    # 1) 移动 mp4 到 downloads/{title}.mp4
    final_mp4 = DOWNLOADS / f"{t}.mp4"
    if mp4.resolve() != final_mp4.resolve():
        shutil.move(str(mp4), str(final_mp4))

    # 2) 转写 md -> transcripts/{title}.md，且内部 H1 标题替换
    final_md = TRANSCRIPTS / f"{t}.md"
    content = tmp_md.read_text(encoding="utf-8")
    content = re.sub(r"^# .*", f"# {t} 逐字稿", content, count=1, flags=re.M)
    final_md.write_text(content, encoding="utf-8")
    tmp_md.unlink(missing_ok=True)

    # 3) 桌面交付 {title}-逐字稿.md
    desk_md = DESKTOP / f"{t}-逐字稿.md"
    shutil.copy2(str(final_md), str(desk_md))

    # 4) 记录 history
    h = load_history()
    if video_id:
        h[video_id] = {"title": t, "mp4": str(final_mp4), "md": str(final_md),
                       "at": time.strftime("%Y-%m-%d %H:%M")}
        save_history(h)

    log(f"交付完成:\n  桌面: {desk_md}\n  工作区: {final_md}\n  mp4: {final_mp4}")
    log("请验证: Read 桌面 md 确认标题正确、简体保持、内容完整。")


def main():
    ap = argparse.ArgumentParser(description="小鹅通回放下载转写流水线")
    ap.add_argument("--m3u8", help="猫抓复制的 m3u8 完整 URL（模式 A）")
    ap.add_argument("--mp4", help="本地 mp4 路径（模式 B 直转）")
    ap.add_argument("--finalize", action="store_true", help="收尾模式：给定标题命名+交付")
    ap.add_argument("--tmp", help="finalize 模式：转写中间 .tmp md 路径")
    ap.add_argument("--title", default="", help="真实标题（播放页 document.title）")
    ap.add_argument("--model", default="large-v3", help="Whisper 模型，默认 large-v3")
    args = ap.parse_args()

    # ---- finalize 模式 ----
    if args.finalize:
        if not args.tmp or not args.mp4 or not args.title:
            raise SystemExit("finalize 需要 --tmp --mp4 --title")
        video_id = ""
        finalize(Path(args.tmp), Path(args.mp4), args.title, video_id)
        return

    # ---- 模式 A / B ----
    video_id = ""
    mp4 = None
    if args.m3u8:
        video_id = extract_video_id(args.m3u8)
        dup, rec = check_duplicate(video_id)
        if dup:
            log(f" 同视频重复: video_id={video_id}，已下载于 {rec.get('at','?')} 标题【{rec.get('title','?')}】")
            log("这是同一视频的新签名（sign/t 参数不同），拒绝重复下载转写。")
            log("如需确认，请比对 ffprobe 时长或抽音频指纹（见 references/download-recipes.md）。")
            sys.exit(2)
        log(f"video_id={video_id}，未在历史记录中，放行下载")
        mp4 = download_m3u8(args.m3u8, video_id)
    elif args.mp4:
        mp4 = Path(args.mp4)
        if not mp4.exists():
            raise SystemExit(f"[错误] mp4 不存在: {mp4}")
        log("模式 B：直转已有 mp4")
    else:
        raise SystemExit("必须提供 --m3u8 或 --mp4")

    info = verify_video(mp4)
    log(f"ffprobe 验证: duration={info.get('duration')}s size={info.get('size')}")

    tmp_md = transcribe(mp4, args.model)
    log(f"转写完成: {tmp_md}")

    # ---- 命名决策 ----
    if args.title:
        finalize(tmp_md, mp4, args.title, video_id)
    else:
        log("未提供 --title。请先 Read 转写内容推断主题命名（带【待核对】），"
            "再运行: python pipeline.py --finalize --tmp <该md> --mp4 <mp4> --title \"推断标题【待核对】\"")
        log(f"中间产物: tmp_md={tmp_md}  mp4={mp4}")


if __name__ == "__main__":
    main()
