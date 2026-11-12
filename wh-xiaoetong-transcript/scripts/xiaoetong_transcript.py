"""
小鹅通口播视频 -> 段落级时间戳逐字稿
=====================================
基于 faster-whisper (默认 large-v3) 本地转写，专治【无字幕、只有声音】的口播课程视频。
把模型输出的句级片段按【静音停顿 + 句末标点】合并成段落，每段一个时间戳，
输出 Markdown 逐字稿，适合学习/复习/进道法术器拆解。

用法示例
--------
    python xiaoetong_transcript.py "./videos\第01讲.mp4"
    python xiaoetong_transcript.py "./videos\audio.m4a" --model small --gap 0.8
    python xiaoetong_transcript.py "./videos\e.mp4" --out "./output\逐字稿.md"

依赖：Python 3.10+、faster-whisper、ctranslate2、ffmpeg。
首次运行会自动下载模型权重: large-v3 约 3GB(需科学上网提速), 可先 --model small(约 460MB) 试用。

依赖检查: faster-whisper 未装时先执行: pip install faster-whisper
"""
import argparse
import sys
import time
from pathlib import Path

# Windows 控制台 UTF-8 适配（VS Code / Windows Terminal 下不乱码）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 句中/句末标点（用于语义分段判断）
SENT_END = set("。！？…；：!?;:")

def ts(seconds: float) -> str:
    """秒 -> HH:MM:SS"""
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def pick_device():
    """GPU 可用则 cuda(float16)，否则 cpu(int8)。"""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"

def merge_segments(segs, gap: float, max_dur: float):
    """
    把句级 segment 合并成语义段落。返回 [{start, end, text}, ...]

    任一条件满足即开新段:
      1) 与上一句间隔 > gap 秒（大停顿）
      2) 上一句以句末标点结尾 且 间隔 > 0.4 秒（小停顿 + 语义边界）
      3) 当前段落累计时长 > max_dur 秒（段落过长防超长）
    """
    paras = []
    cur = None  # {"start": 段首句start, "end": 当前句end, "prev_end":上一句end, "text": 拼接文本}

    def flush():
        nonlocal cur
        if cur is not None:
            paras.append(cur)
            cur = None

    for seg in segs:
        text = (seg.text or "").strip()
        if not text:
            continue
        if cur is None:
            cur = {"start": seg.start, "end": seg.end, "prev_end": seg.end, "text": text}
            continue

        gap_prev = seg.start - cur["prev_end"]
        prev_text = cur["text"]
        prev_end_char = prev_text[-1] if prev_text else ""
        should_split = (
            gap_prev > gap
            or (prev_end_char in SENT_END and gap_prev > 0.4)
            or (seg.end - cur["start"]) > max_dur
        )
        if should_split:
            flush()
            cur = {"start": seg.start, "end": seg.end, "prev_end": seg.end, "text": text}
        else:
            cur["end"] = seg.end
            cur["prev_end"] = seg.end
            cur["text"] += text

    flush()
    return paras

def main():
    ap = argparse.ArgumentParser(description="小鹅通口播视频/音频 -> 段落级时间戳逐字稿")
    ap.add_argument("input", help="本地视频或音频文件路径 (mp4/m4a/mp3/wav 等 ffmpeg 支持的格式)")
    ap.add_argument("--model", default="large-v3", help="Whisper 模型: large-v3(最准,默认) / medium / small(最快,约460MB)")
    ap.add_argument("--lang", default="zh", help="语言代码，默认 zh（中文）")
    ap.add_argument("--gap", type=float, default=1.0, help="段落合并静音阈值(秒)，默认 1.0，越大段落越长")
    ap.add_argument("--max-dur", type=float, default=90.0, help="段落最长时长(秒)，默认 90，防单段过长")
    ap.add_argument("--out", default=None, help="输出 md 路径；默认在输入同目录生成 {名字}_逐字稿.md")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"[错误] 文件不存在: {src}")
    if not args.out:
        args.out = str(src.with_name(src.stem + "_逐字稿.md"))

    t0 = time.time()
    device, compute_type = pick_device()
    print(f"[1/3] 加载模型 {args.model} (device={device}, compute={compute_type}) ...", flush=True)
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(args.model, device=device, compute_type=compute_type)
    except Exception as e:
        sys.exit(f"[错误] 模型加载失败: {e}\n提示: 若为网络问题，请给终端配置代理后重试；或先改用 --model small。")

    print(f"[2/3] 转写中 ... (音频总长 {src.stat().st_size / 1024 / 1024:.1f} MB)", flush=True)
    segments, info = model.transcribe(
        str(src),
        language=args.lang,
        vad_filter=True,          # 过滤静音段，对口播更干净
        beam_size=5,              # 准确率与速度折中
    )
    raw = [(s.start, s.end, s.text) for s in segments]  # 物化迭代器
    audio_dur = getattr(info, "duration", None) or (raw[-1][1] if raw else 0)

    paras = merge_segments(
        [type("S", (), {"start": a, "end": b, "text": c}) for a, b, c in raw],
        gap=args.gap,
        max_dur=args.max_dur,
    )

    if not paras:
        sys.exit("[错误] 没有转写出任何文本。请确认音频有清晰人声，或换 --model large-v3 提高识别率。")

    # 繁转简清洗（opencc t2s）：whisper 输出可能带繁体字形，统一转简体。
    # 未安装 opencc 时降级为原样输出并提示，不阻断流程。
    try:
        from opencc import OpenCC
        _cc = OpenCC("t2s")
        for _p in paras:
            _p["text"] = _cc.convert(_p["text"])
    except ImportError:
        print("[提示] 未安装 opencc，跳过繁转简（逐字稿可能含繁体）。装：pip install opencc-python-reimplemented", flush=True)

    lines = [
        f"# {src.stem} 逐字稿",
        "",
        f"> 引擎: faster-whisper {args.model} | 段落=静音>{args.gap}s + 句末标点 | 音频时长 {ts(audio_dur)} | 段落数 {len(paras)}",
        f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M')} | 仅供个人学习使用",
        "",
        "## 逐字稿",
        "",
    ]
    for p in paras:
        lines.append(f"[{ts(p['start'])} - {ts(p['end'])}]")
        lines.append("")
        lines.append(p["text"])
        lines.append("")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")

    print(f"[3/3] 完成: {args.out}  (耗时 {time.time() - t0:.0f}s, 段落数 {len(paras)})", flush=True)

if __name__ == "__main__":
    main()