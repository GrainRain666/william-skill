#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xe_doctor.py — wh-xiaoetong-harvest 环境体检

用法：
    python xe_doctor.py

输出 PASS / WARN / FAIL 清单，FAIL 项给出修复动作。全 PASS 才进入采集与下载。
"""
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).resolve().parent.parent
TABBIT_CLI = Path.home() / "AppData/Local/Tabbit/LocalAgent/bin/tabbit-cli.exe"
VAULT = Path.home() / "Documents/Xiaoetong"
VAULT_ROOT = VAULT.parent
ARCHIVE = Path.home() / "Documents/Xiaoetong-archive"


def check_ffmpeg():
    p = shutil.which("ffmpeg")
    if not p:
        return "FAIL", "ffmpeg 不在 PATH", "winget install Gyan.FFmpeg 或安装后加入 PATH"
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=20)
        ver = (r.stdout or "").splitlines()[0] if r.stdout else ""
        return "PASS", f"ffmpeg 就绪（{ver[:60]}）", ""
    except Exception as exc:
        return "FAIL", f"ffmpeg 无法执行: {exc}", "检查 PATH 与杀软拦截"


def check_ffprobe():
    p = shutil.which("ffprobe")
    if not p:
        return "FAIL", "ffprobe 不在 PATH", "随 ffmpeg 一起安装（Gyan.FFmpeg full build）"
    return "PASS", "ffprobe 就绪", ""


def check_tabbit():
    if TABBIT_CLI.exists():
        return "PASS", f"tabbit-cli 就绪 {TABBIT_CLI}", ""
    return "WARN", "tabbit-cli 未找到（若不用 tabbit 提供登录态可忽略）", "确认 Tabbit 已安装并登录配对"


def check_userscript():
    p = SKILL_DIR / "scripts" / "userscript" / "xiaoe-course-harvest.user.js"
    if p.exists():
        return "PASS", f"油猴脚本就位 {p}", ""
    return "FAIL", "油猴脚本缺失", "重新安装 wh-xiaoetong-harvest 技能包"


def check_vault():
    if not VAULT.exists():
        return "FAIL", f"Obsidian 目录不存在：{VAULT}", "确认路径；vault 根在上级目录"
    if (VAULT_ROOT / ".obsidian").is_dir():
        return "PASS", f"Obsidian 就绪：{VAULT}（库根 {VAULT_ROOT}）", ""
    return "WARN", f"{VAULT} 存在，但库根 {VAULT_ROOT} 未见 .obsidian", f"确认 Obsidian 已把 {VAULT_ROOT} 打开为库"


def check_archive():
    if ARCHIVE.exists():
        return "PASS", f"归档根就绪 {ARCHIVE}", ""
    return "WARN", f"归档根不存在 {ARCHIVE}（obsidian 阶段会自动创建）", ""


def check_nre():
    p = shutil.which("N_m3u8DL-RE")
    if p:
        return "PASS", f"N_m3u8DL-RE 可用 {p}（--engine nre 可选）", ""
    return "WARN", "N_m3u8DL-RE 未安装（可选，默认引擎 ffmpeg 已足够）", "如需：github.com/nilaoda/N_m3u8DL-RE/releases"


def check_transcribe():
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return "WARN", "faster-whisper 未安装（transcribe 阶段不可用，下载整理不受影响）", "pip install faster-whisper opencc-python-reimplemented"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "PASS", "faster-whisper + GPU 就绪（transcribe 阶段可用）", ""
        return "WARN", "faster-whisper 就绪但无 CUDA（转写将走 CPU，慢约 20 倍）", "检查显卡驱动 / ctranslate2 CUDA 支持"
    except Exception:
        return "PASS", "faster-whisper 就绪", ""


def check_disk():
    try:
        import shutil as _sh
        free = _sh.disk_usage(VAULT if VAULT.exists() else Path.home()).free / 1024 / 1024 / 1024
        if free < 10:
            return "WARN", f"目标磁盘剩余 {free:.1f} GiB（90 分钟 1080p 约占 1.5 GiB/节）", "清理目标磁盘后批量下载"
        return "PASS", f"目标磁盘剩余 {free:.1f} GiB", ""
    except Exception as exc:
        return "WARN", f"磁盘检查失败: {exc}", ""


def main():
    checks = [
        ("python", "PASS", f"{sys.version_info.major}.{sys.version_info.minor}", ""),
        ("ffmpeg", *check_ffmpeg()),
        ("ffprobe", *check_ffprobe()),
        ("tabbit-cli", *check_tabbit()),
        ("userscript", *check_userscript()),
        ("obsidian", *check_vault()),
        ("archive", *check_archive()),
        ("n_m3u8dl-re", *check_nre()),
        ("transcribe", *check_transcribe()),
        ("disk", *check_disk()),
    ]
    fail = 0
    print("=== wh-xiaoetong-harvest 环境体检 ===")
    for name, level, detail, fix in checks:
        if name == "python":
            level = "PASS"
            detail = f"python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        mark = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[level]
        if level == "FAIL":
            fail += 1
        line = f"{mark} {name:<12} {detail}"
        print(line)
        if fix:
            print(f"           修复: {fix}")
    if fail:
        print(f"=== 结果：{fail} 项 FAIL，先修复再进入采集下载 ===")
        sys.exit(1)
    print("=== 结果：无 FAIL 项，可进入采集与下载 ===")


if __name__ == "__main__":
    main()
