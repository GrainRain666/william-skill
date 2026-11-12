# 报错排查手册（troubleshooting）

> 按【现象 → 根因 → 修复】诊断模式。每条来自真实踩坑，不是理论。

---

## 1. cublas64_12.dll is not found（faster-whisper 转写崩溃）

- **现象**：`RuntimeError: Library cublas64_12.dll is not found`
- **根因链**：
  1. `pip install "ctranslate2[cpu]"` 无效——`[cpu]` extra 只附加 numpy，wheel 仍是 CUDA 版（DLL 带 cudnn64_9.dll）
  2. ctranslate2 在 Windows 用 `os.add_dll_directory` 只搜自己的安装目录，不搜 PATH
  3. 本机有真 GPU（RTX 5070 Ti Laptop, sm_120），torch 显示 CPU 是装了 torch+cpu 版误导
- **修复**：
  ```bash
  pip install nvidia-cublas-cu12
  SP=$(python -c "import site; print(site.getsitepackages()[0])")
  cp "$SP/nvidia/cublas/bin/"cublas*.dll "$SP/ctranslate2/"
  cp "$SP/nvidia/cublas/bin/"nvblas*.dll "$SP/ctranslate2/"
  ```
- **验证**：转写日志出现 `device=cuda, compute=float16`

## 2. torch 显示 CPU，以为没 GPU

- **现象**：`torch.cuda.is_available()` 返回 False
- **根因**：装了 `torch+cpu` 版（pip 默认有时解析到 CPU wheel）
- **注意**：faster-whisper 不依赖 torch，它用 ctranslate2 直接调 GPU。所以 torch CPU 版**不影响** faster-whisper 走 GPU。
- **验证 GPU 真正方式**：`python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` > 0 即有 GPU

## 3. Tampermonkey 扩展报错禁用

- **现象**：`chrome://extensions` 卡片红字 `'webRequestBlocking' requires manifest version of 2 or lower` 或 `Permission 'chrome://favicon/' is unknown`
- **根因**：非商店 crx 解压版 manifest 带 MV2 遗留权限
- **修复**：`python scripts/fix_manifest.py --dir "download/extracted/tampermonkey"`（删 webRequestBlocking + chrome://favicon 换 favicon）→ 重新加载扩展
- **无害噪音**：`No tab with id` / `Cannot read properties...replace` 是后台脚本运行期噪音，忽略

## 4. 油猴脚本安装被拦【无法从该网站添加应用、扩展程序和用户脚本】

- **现象**：拖 .user.js 进浏览器，Chromium 拦截
- **根因**：源是 `file://`，Chromium 拒绝从 file 源装脚本
- **修复**：本地 http 服务托管（见 browser-ext-setup.md §二步骤3），或油猴【实用工具→文件导入】

## 5. 下载 403 / 防盗链

- **根因**：缺 Referer 或签名过期
- **修复**：带 `-H "Referer: https://YOUR_XIAOETONG_HOST/"`；签名 `t=` 过期需在浏览器重新复制新 m3u8

## 6. 下载到的是直播流不是回放

- **根因**：m3u8 域名是 `liveplay-byte` / `liveplay.xiaoe-live.com` / `webrtc`
- **修复**：回放必须是 `encrypt-k-vod.xet.tech` 点播域，重新在播放页复制

## 7. 同视频重复下载（video ID 相同）

- **根因**：m3u8 是同一视频的新签名（sign/t 参数不同）
- **修复**：不下载，向用户说明"这是上一节的同视频"（识别法见 download-recipes.md §二）

## 8. 转写全为歌词/无口播

- **现象**：转写内容全是歌曲/说唱
- **根因**：课程开头数分钟是歌曲（课程惯例），small 模型对带音乐说唱识别差
- **修复**：抽 30 分钟处再测口播质量；全量用 large-v3 提高识别率

## 9. 终端中文乱码

- **现象**：MSYS2/Git Bash 下中文输出乱码
- **根因**：MSYS2 locale 层破坏 UTF-8
- **修复**：Python 脚本内 `sys.stdout.reconfigure(encoding="utf-8")`；中文路径操作一律 Python 脚本，禁止 Bash heredoc

## 10. Chrome 扩展无法连接（AI 想读用户浏览器）

- **现象**：AI 尝试连用户 Chrome 看登录态失败
- **根因**：NewMax Chrome 扩展未配对（browser-use 工具 backend=chrome 需要显式配对）
- **边界**：无法获取用户登录态时，课程目录不可见——用【推断名+待核对】交付，或请用户提供播放页标题
