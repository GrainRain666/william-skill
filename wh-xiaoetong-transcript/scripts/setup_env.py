"""
wh-xiaoetong-transcript 环境搭建（自动 85% + 输出人工 15% 指引）
=================================================================
自动：pip 装依赖 + GPU 修复（cublas DLL）+ 就位下载器 + 核验浏览器资产 + 输出人工步骤清单
人工（浏览器安全机制，必须真人）：Tampermonkey/猫抓加载、油猴脚本安装、登录、播放抓 m3u8

用法: python scripts/setup_env.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WS = Path.home() / "Documents/Xiaoetong-Transcript"
DOWNLOADS = WS / "downloads"
DOWNLOADS_S = WS / "download"   # 浏览器扩展资产目录（注意单复数差异：download/）
DOWNLOADER = WS / "downloader/N_m3u8DL-RE/N_m3u8DL-RE.exe"
ASSETS = {
    "油猴脚本": "download/小鹅通-通用m3u8获取.user.js",
    "Tampermonkey crx": "download/tampermonkey.crx",
    "Tampermonkey 解压目录": "download/extracted/tampermonkey",
    "猫抓 crx": "download/cat-catch-2.7.2-chrome.crx",
    "猫抓解压目录": "download/extracted/catcatch",
}

ok, warn, fail = [], [], []


def report(kind, msg):
    print(f"  [{kind:>4}] {msg}", flush=True)
    {"OK": ok, "WARN": warn, "FAIL": fail}[kind].append(msg)


def pip_install(pkg: str):
    r = subprocess.run([sys.executable, "-m", "pip", "install", pkg],
                       capture_output=True, text=True)
    return r.returncode == 0


def main():
    print("== wh-xiaoetong-transcript 环境搭建 ==", flush=True)

    # 1) Python 版本
    v = sys.version_info
    if v >= (3, 10):
        report("OK", f"Python {v.major}.{v.minor}.{v.micro} >= 3.10")
    else:
        report("FAIL", f"Python {v.major}.{v.minor} < 3.10，请升级")

    # 2) Python 依赖（缺则装）
    deps = ["faster-whisper", "ctranslate2", "opencc-python-reimplemented"]
    for d in deps:
        try:
            __import__(d.replace("-", "_"))
            report("OK", f"依赖已装: {d}")
        except ImportError:
            report("WARN", f"缺 {d}，自动安装中...")
            if pip_install(d):
                report("OK", f"已装 {d}")
            else:
                report("FAIL", f"{d} 安装失败，手动跑: pip install {d}")

    # 3) GPU 检测 + cublas 修复
    try:
        import ctranslate2
        cnt = ctranslate2.get_cuda_device_count()
        if cnt > 0:
            report("OK", f"检测到 GPU (ctranslate2 cuda count={cnt})")
            # 用 ctranslate2.__file__ 定位包目录（site.getsitepackages()[0] 在 Windows 上缺 Lib\site-packages）
            ct_dir = Path(ctranslate2.__file__).resolve().parent
            sp_dir = ct_dir.parent  # 真正的 site-packages
            cublas_dir = sp_dir / "nvidia/cublas/bin"
            if not list(ct_dir.glob("cublas64*.dll")):
                if not cublas_dir.exists():
                    report("WARN", "缺 nvidia-cublas-cu12，自动安装...")
                    pip_install("nvidia-cublas-cu12")
                if cublas_dir.exists():
                    ct_dir.mkdir(parents=True, exist_ok=True)
                    n = 0
                    for pat in ("cublas*.dll", "nvblas*.dll"):
                        for f in cublas_dir.glob(pat):
                            shutil.copy2(str(f), str(ct_dir / f.name))
                            n += 1
                    report("OK", f"已复制 {n} 个 cublas/nvblas DLL 到 ctranslate2/")
                else:
                    report("FAIL", "cublas 包安装后仍未找到 DLL，手动排查")
            else:
                report("OK", "cublas DLL 已在 ctranslate2/ 目录")
        else:
            report("WARN", "ctranslate2 未检测到 GPU，转写将走 CPU（慢 ~20 倍）")
    except Exception as e:
        report("WARN", f"GPU 检测异常: {e}（不阻断，CPU 可用）")

    # 4) ffmpeg
    if shutil.which("ffmpeg"):
        report("OK", f"ffmpeg: {shutil.which('ffmpeg')}")
    else:
        report("FAIL", "ffmpeg 不在 PATH，请从官方 ffmpeg.org 安装（勿用非官方源）")

    # 5) N_m3u8DL-RE
    if DOWNLOADER.exists():
        report("OK", f"N_m3u8DL-RE: {DOWNLOADER}")
    else:
        report("FAIL", "N_m3u8DL-RE 缺失，来源: github.com/nilaoda/N_m3u8DL-RE releases")

    # 6) large-v3 模型缓存
    hf = Path.home() / ".cache/huggingface"
    if any(hf.rglob("large-v3")) if hf.exists() else False:
        report("OK", "large-v3 模型权重已缓存")
    else:
        report("WARN", "large-v3 未缓存（首次转写下载 ~3GB），可先用 --model small 验证")

    # 7) 浏览器扩展资产
    for name, rel in ASSETS.items():
        p = WS / rel
        report("OK" if p.exists() else "FAIL", f"{name}: {'就位' if p.exists() else '缺失 ' + str(p)}")

    # 8) 输出人工步骤清单
    guide = WS / "人工步骤清单.md"
    lines = [
        "# 人工步骤清单（setup_env.py 生成，必须真人完成）",
        "",
        "> 以下 5 步是浏览器安全机制，任何程序无法代点。完成后再跑 verify_env.py 确认。",
        "",
        "| 步 | 动作 | 精确指引 | 预期现象 |",
        "|----|------|---------|---------|",
        "| 1 | 装 Tampermonkey | Chrome 打开 chrome://extensions → 开发者模式 → 加载已解压 → 选 download/extracted/tampermonkey/ | 扩展卡片无红字，开关可开 |",
        "| 2 | 装猫抓 | 同上 → 加载 download/extracted/catcatch/ | 工具栏出现猫抓图标 |",
        "| 3 | 装油猴脚本 | 先 `python -m http.server 8543 --bind 127.0.0.1`，再访问 http://127.0.0.1:8543/小鹅通-通用m3u8获取.user.js → 安装 | 油猴弹安装页 |",
        "| 4 | 登录小鹅通 | 浏览器打开课程页登录 | 课程目录可见 |",
        "| 5 | 抓 m3u8 | 进回放页点播放几秒 → 点猫抓图标 | 猫抓列表出现 m3u8 |",
        "",
        "详细图文见 skill references/browser-ext-setup.md",
    ]
    guide.write_text("\n".join(lines), encoding="utf-8")
    report("OK", f"已生成人工步骤清单: {guide}")

    # 9) 汇总
    print("\n== 汇总 ==", flush=True)
    print(f"  OK   {len(ok)} 项", flush=True)
    print(f"  WARN {len(warn)} 项（建议处理）", flush=True)
    print(f"  FAIL {len(fail)} 项（必须先修）", flush=True)
    if fail:
        print("\nFAIL 项处理完再跑 verify_env.py", flush=True)
        sys.exit(1)
    print("\n环境就绪（自动段）。人工 5 步完成后即可使用。", flush=True)


if __name__ == "__main__":
    main()
