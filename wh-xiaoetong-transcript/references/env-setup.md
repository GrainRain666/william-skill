# 环境搭建（setup_env.py 自动段 + 人工段分章）

> 给新人"完全复刻全部流程"的环境手册。自动 85%（setup_env.py），人工 15%（浏览器安全机制）。
> 原则：能自动的绝不让手动，必须人工的给到按钮级精确指引。

---

## 一、环境总览（分两类）

| 环节 | 能否自动化 | 工具 | 状态判定 |
|------|-----------|------|---------|
| Python 依赖 |  | setup_env.py pip 安装 | verify_env.py |
| GPU 修复（cublas DLL） |  | setup_env.py 自动复制 | verify_env.py |
| ffmpeg |  检测已有，缺则指路 | verify_env.py | PATH 检测 |
| N_m3u8DL-RE 下载器 |  从资产复制 | setup_env.py | verify_env.py |
| large-v3 模型 |  触发下载 | setup_env.py | HF 缓存检测 |
| Tampermonkey/猫抓扩展 |  必须真人点 | 人工段（browser-ext-setup.md） | 浏览器验证 |
| 油猴脚本安装 |  必须真人点 | 人工段 | 红色角标验证 |
| 登录小鹅通 + 播放抓 m3u8 |  必须真人做 | 人工段 | 猫抓见 m3u8 |

## 二、setup_env.py 自动行为清单

1. **Python 检测**：要求 ≥ 3.10，缺则提示安装
2. **依赖安装**（pip，缺则装）：
   - `faster-whisper`（转写引擎）
   - `ctranslate2`（faster-whisper 底层）
   - `opencc-python-reimplemented`（繁转简）
   - `torch`（GPU 检测；本机实际是 CPU 版不影响 faster-whisper）
3. **GPU 修复**（关键）：
   - 检测 `ctranslate2.get_cuda_device_count() > 0` 但 `device=cuda` 加载失败
   - 失败原因通常是 `cublas64_12.dll is not found`
   - 自动执行：
     ```bash
     pip install nvidia-cublas-cu12
     # 复制 DLL 到 ctranslate2 目录（os.add_dll_directory 只搜自己目录）
     SP=$(python -c "import site; print(site.getsitepackages()[0])")
     cp "$SP/nvidia/cublas/bin/"cublas*.dll "$SP/ctranslate2/"
     cp "$SP/nvidia/cublas/bin/"nvblas*.dll "$SP/ctranslate2/"
     ```
   - **为什么 PATH 无效**：ctranslate2 在 Windows 用 `os.add_dll_directory` 只搜自己安装目录，不搜 PATH（README-油猴猫抓下载方案.md#155-172）
4. **ffmpeg**：检测 PATH（`ffmpeg -version`），缺则输出官方源指引（ffmpeg.org，**禁止非官方源**）
5. **N_m3u8DL-RE**：检测 `outputs/小鹅通转写工作流/downloader/`，缺则提示来源（GitHub nilaoda/N_m3u8DL-RE releases）
6. **large-v3 模型**：检测 HF 缓存（`~/.cache/huggingface`），缺则提示首次转写会下载 3GB（或手动 `huggingface-cli download Systran/faster-whisper-large-v3`）
7. **浏览器资产核验**：检测 `download/` 五件资产（见 _meta.json assets_registry），缺则提示来源
8. **输出 `人工步骤清单.md`**：列必须真人做的 5 步（见下）

## 三、人工 5 步（必须真人，setup_env 输出清单引导）

| 步 | 动作 | 精确指引 | 预期现象 |
|----|------|---------|---------|
| 1 | 装 Tampermonkey | Chrome 打开 `chrome://extensions` → 开发者模式 → 加载已解压 → 选 `download/extracted/tampermonkey/` | 扩展卡片无红字，开关可开 |
| 2 | 装猫抓 | 同上 → 加载 `download/extracted/catcatch/` | 工具栏出现猫抓图标 |
| 3 | 装油猴脚本 | 地址栏访问 `http://127.0.0.1:8543/小鹅通-通用m3u8获取.user.js`（先起本地服务）→ 点安装 | 油猴弹安装页 |
| 4 | 登录小鹅通 | 浏览器打开课程页登录 | 课程目录可见 |
| 5 | 抓 m3u8 | 进回放页点播放几秒 → 点猫抓图标 → 看到 m3u8 资源 | 猫抓列表出现 m3u8 |

> 浏览器扩展全细节（含 Tabbit 备选、manifest 权限修复、file:// 拦截问题）→ `browser-ext-setup.md`

## 四、验证

- `python scripts/verify_env.py` → 输出 PASS/FAIL 清单
- 全 PASS = 环境就绪，可进下载/转写
- FAIL 项给出修复动作（不是报错卡死）

## 五、本机已验证基线（2026-09）

- Python 3.11.9 + faster-whisper 1.2.1 + ctranslate2 4.8.1 + ffmpeg 8.1.2（Gyan 版）
- GPU：RTX 5070 Ti Laptop（12GB, Blackwell, sm_120），cuda/float16 生效
- 模型：large-v3 权重已缓存（3GB，后续免重下）

## 六、反模式

| 反模式 | 后果 | 正确做法 |
|--------|------|---------|
| `pip install ctranslate2[cpu]` 期望换 CPU wheel | `[cpu]` extra 只是附加依赖，wheel 仍 CUDA 版 | 直接装 nvidia-cublas-cu12 补 DLL |
| 把 cublas DLL 目录加 PATH | ctranslate2 不搜 PATH | 复制 DLL 到 ctranslate2 安装目录 |
| 从非官方源下 ffmpeg | 安全风险 | 只用 ffmpeg.org 或已装的 Gyan 版 |
| 试图远程代装浏览器扩展 | 跨进程不可行 | 人工 5 步，精确指引 |
