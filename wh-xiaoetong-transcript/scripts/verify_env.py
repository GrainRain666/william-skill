"""
wh-xiaoetong-transcript 环境就绪验证
====================================
输出 PASS/FAIL 清单，FAIL 项给出修复动作（不是报错卡死）。
用法: python scripts/verify_env.py
"""
import json
import shutil
import site
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WS = Path.home() / "Documents/Xiaoetong-Transcript"
CHECKS = []


def check(name, ok, fix_hint=""):
    CHECKS.append((name, ok, fix_hint))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  -> 修复: {fix_hint}" if not ok and fix_hint else ""), flush=True)


def main():
    print("== wh-xiaoetong-transcript 环境验证 ==", flush=True)

    # Python
    v = sys.version_info
    check("Python >= 3.10", v >= (3, 10), f"当前 {v.major}.{v.minor}，请升级")

    # ffmpeg
    ff = shutil.which("ffmpeg")
    check("ffmpeg 在 PATH", bool(ff), "从 ffmpeg.org 官方安装")

    # faster-whisper
    try:
        import faster_whisper
        check("faster-whisper", True)
    except ImportError:
        check("faster-whisper", False, "pip install faster-whisper")

    # ctranslate2 GPU
    gpu_ok = False
    try:
        import ctranslate2
        cnt = ctranslate2.get_cuda_device_count()
        ct_dir = Path(ctranslate2.__file__).resolve().parent
        has_dll = bool(list(ct_dir.glob("cublas64*.dll")))
        gpu_ok = cnt > 0 and has_dll
        if cnt > 0 and not has_dll:
            check("ctranslate2 GPU DLL", False, "跑 setup_env.py（复制 cublas DLL 到 ctranslate2/ 目录）")
        else:
            check(f"ctranslate2 GPU (cuda={cnt}, dll={'有' if has_dll else '无'})", cnt > 0,
                  "无 GPU 则 CPU 转写（慢 20 倍）")
    except ImportError:
        check("ctranslate2", False, "pip install ctranslate2")

    # opencc
    try:
        from opencc import OpenCC
        OpenCC("t2s")
        check("opencc 繁转简", True)
    except ImportError:
        check("opencc 繁转简", False, "pip install opencc-python-reimplemented")

    # N_m3u8DL-RE
    dl = WS / "downloader/N_m3u8DL-RE/N_m3u8DL-RE.exe"
    check("N_m3u8DL-RE", dl.exists(), "从 github.com/nilaoda/N_m3u8DL-RE releases 下载")

    # large-v3 模型
    hf = Path.home() / ".cache/huggingface"
    model_cached = hf.exists() and any(p.name == "model.bin" and "large-v3" in str(p)
                                       for p in hf.rglob("*"))
    check("large-v3 模型缓存", model_cached, "首次转写自动下载 ~3GB，或先 --model small")

    # 浏览器扩展资产
    assets = {
        "油猴脚本 .user.js": "download/小鹅通-通用m3u8获取.user.js",
        "Tampermonkey 解压目录": "download/extracted/tampermonkey",
        "猫抓解压目录": "download/extracted/catcatch",
    }
    for name, rel in assets.items():
        check(name, (WS / rel).exists(), f"缺失 {WS / rel}，见 _meta.json assets_registry 来源")

    # 汇总
    n_pass = sum(1 for _, ok, _ in CHECKS if ok)
    n_fail = len(CHECKS) - n_pass
    print(f"\n== 结果: PASS {n_pass} / FAIL {n_fail} ==", flush=True)
    if n_fail:
        print("FAIL 项按修复动作处理后重跑本脚本。浏览器扩展人工段见 references/browser-ext-setup.md", flush=True)
        sys.exit(1)
    print("环境全就绪。可进入 pipeline.py（--m3u8 或 --mp4）。", flush=True)


if __name__ == "__main__":
    main()
