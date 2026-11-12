# wh-xiaoetong-transcript 黄金规则

> 来源：2026-08-31 ~ 09-02 三节实战 + 自研逆向 5 轮失败复盘。每条必须可执行、有来源、有反模式。

## 规则 1：前端拦截优先于后端逆向（最高优先级）

- **内容**：小鹅通回放地址 = 登录态 + 签名 + 播放器运行时二次请求。自研 API 逆向已 5 轮验证失败（结构墙，工程法则 9）。
- **正确做法**：油猴脚本【小鹅通通用m3u8获取】+ 猫抓扩展，在浏览器运行时抓真实 m3u8（天然带签名）。
- **反模式**：再次尝试 Electron/CDP 逆向小鹅通 API。
- **来源**：negative-results.md v1-v5；Source: <WORK_DIR>\negative-results.md#7-14

## 规则 2：命名必须真实标题，推断名强制标注【待核对】

- **内容**：文件名必须来自用户给的播放页标题（document.title）；只有 m3u8 没有标题时，用内容推断命名但必须带【待核对】，交付时明说。
- **正确做法**：`{序号}.{YYYY.M.D}-{真实标题}.md`；推断名格式 `{YYYY.M.D}-{主题推断}-【待核对】.md`
- **反模式**：凭印象起名（"2025.9.7 浪前重聚"更名事故——误导用户两天）。
- **来源**：52 节更名事故；Source: memory/2026-09-01.md

## 规则 3：下载前必查 video ID 防重复

- **内容**：m3u8 URL 路径中 `/{id}vodcq/` 段是视频 ID。video ID 相同 = 同视频新签名（不同 sign/t 参数），拒绝重复下载转写。
- **正确做法**：下载前对比 `downloads/` 已有 mp4 的 video ID + ffprobe 时长；存疑时抽音频指纹（同时间段 10 秒 PCM md5）对比。
- **反模式**：用户发来新链接直接下载——同视频重复浪费 1.6GB + 几小时。
- **来源**：第 2 次"再转写一个"收到同视频新签名；Source: memory/2026-09-02.md

## 规则 4：GPU 优先，缺 DLL 先修再跑

- **内容**：本机有 RTX 5070 Ti Laptop（12GB, Blackwell）。faster-whisper 走 GPU（cuda/float16）约 7 分钟/90 分钟视频，CPU 慢 20 倍。
- **正确做法**：先跑 `verify_env.py` 确认 `device=cuda`；缺 cublas64_12.dll 时从 `nvidia-cublas-cu12` 复制 DLL 到 ctranslate2 目录。
- **反模式**：环境报 cublas 缺失就降级 CPU 硬跑，或误以为没 GPU。
- **来源**：GPU 修复记录；Source: README-油猴猫抓下载方案.md#155-172

## 规则 5：繁转简是默认动作，不是可选项

- **内容**：faster-whisper 输出可能带繁体字形，转写后必须 opencc t2s 转简体。
- **正确做法**：转写脚本内置 `OpenCC("t2s")`，未装 opencc 时提示但不阻断。
- **反模式**：交付繁体逐字稿让用户手动提需求。
- **来源**：用户反馈"逐字稿有繁体"；Source: memory/2026-09-01.md

## 规则 6：环境配置 = 自动 85% + 人工 15%，边界分明

- **内容**：Python 依赖、GPU 修复、下载器就位可自动化；Tampermonkey/猫抓加载、登录、播放抓 m3u8 必须真人做（浏览器安全机制）。
- **正确做法**：setup_env.py 输出 `人工步骤清单.md`，每步给精确路径/按钮名/预期现象。
- **反模式**：试图远程代点浏览器安装（跨进程不可行），或让新人自己摸索装扩展。
- **来源**：环境搭建实战；Source: README-油猴猫抓下载方案.md#38-69

## 规则 7：ffprobe 验证通过才算"下载完成"

- **内容**：下载完成后必须 ffprobe 验证时长/分辨率/大小，确认与 m3u8 声明一致、分片无缺失。
- **正确做法**：`ffprobe -v error -show_entries format=duration,size:stream=codec_name -of default=noprint_wrappers=1 <file>`
- **反模式**：N_m3u8DL-RE 退出码 0 就直接声称完成，不验证产物。
- **来源**：三节下载验证流程；Source: README-油猴猫抓下载方案.md#146-153

## 规则 8：脚本黑盒化，用 --help 不读源码

- **内容**：scripts/ 下脚本是黑盒工具（pipeline/setup_env/verify_env/fix_manifest），调用前跑 `--help` 看参数。
- **正确做法**：`python scripts/pipeline.py --help` → 按参数调用。
- **反模式**：把 1000 行脚本读进上下文再手写调用。
- **来源**：li-webtest 黑盒模式。

## 规则 9：负结果必须归档

- **内容**：任何验证为死路的方案（自研逆向、批量无人爬取）必须写进 references/negative-results.md，含方案/失败现象/退出判据。
- **正确做法**：失败当轮归档，不等到对话结束。
- **反模式**：死路靠记忆，下个会话重新踩。
- **来源**：工程法则 7；negative-results.md
