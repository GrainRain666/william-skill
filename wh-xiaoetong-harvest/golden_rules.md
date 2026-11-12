# wh-xiaoetong-harvest 黄金规则

> 来源：wh-xiaoetong-transcript 社区包三节实战 + 自研逆向 5 轮失败复盘（2026-08-31 ~ 09-02）+
> 2026-09-03 批量化改造实战。每条必须可执行、有来源、有反模式。规则 1-6 继承社区包，7-12 为本技能新增。

## 规则 1：前端拦截优先于后端逆向（最高优先级）

- **内容**：小鹅通回放地址 = 登录态 + 签名 + 播放器运行时二次请求。自研 API 逆向已 5 轮验证失败（结构墙）。
- **正确做法**：油猴脚本 hook JSON.parse/XHR/indexOf 在浏览器运行时抓真实 m3u8（天然带签名），AI 只负责开页与监控。
- **反模式**：再次尝试 Electron/CDP/纯 requests 逆向小鹅通 API。
- **来源**：negative-results.md 负结果 1（v1-v5 全记录）。

## 规则 2：命名必须真实标题，推断名强制标注【待核对】

- **内容**：文件名必须来自课程目录页显示名称（采集清单 title 字段）；无标题时才允许内容推断并强制带【待核对】。
- **正确做法**：`{标题}.md` 与 `{标题}.mp4` 同名同目录；organize 阶段统一命名，下载产物用 video_id 过渡。
- **反模式**：凭印象起名（"2025.9.7 浪前重聚"更名事故，误导用户两天）。
- **来源**：52 节更名事故；wh-xiaoetong-transcript golden_rules 规则 2。

## 规则 3：下载前必查 CDN video ID 防重复

- **内容**：encrypt-k-vod 域 m3u8 URL 路径中 `/{id}vodcq/` 段是视频 ID；v-vod-k drm 域取路径倒数第二段。video ID 相同 = 同视频新签名，拒绝重复下载。
- **正确做法**：history.json 以 video_id 为主键、CDN id 为副键；命中即 [block]。
- **反模式**：用户发来新链接直接下载——同视频重复浪费 1.6GB + 几小时。
- **来源**：第 2 次"再转写一个"收到同视频新签名；download-recipes.md 案例二。

## 规则 4：转写 GPU 优先，缺 DLL 先修再跑

- **内容**：faster-whisper 走 GPU（cuda/float16）约 7 分钟/90 分钟视频，CPU 慢 20 倍。
- **正确做法**：先跑 `xe_doctor.py` 确认 CUDA；缺 cublas64_12.dll 时从 `nvidia-cublas-cu12` 复制 DLL 到 ctranslate2 目录。
- **反模式**：环境报 cublas 缺失就降级 CPU 硬跑。
- **来源**：wh-xiaoetong-transcript golden_rules 规则 4。

## 规则 5：繁转简是默认动作，不是可选项

- **内容**：faster-whisper 输出可能带繁体字形，转写后必须 opencc t2s 转简体。
- **正确做法**：xiaoetong_transcript.py 已内置 OpenCC("t2s")；未装 opencc 时提示但不阻断。
- **反模式**：交付繁体逐字稿让用户手动提需求。
- **来源**：用户反馈"逐字稿有繁体"；2026-09-01 memory。

## 规则 6：环境配置 = 自动 85% + 人工 15%，边界分明

- **内容**：Python 依赖、下载引擎、目录同步可自动化；扩展安装确认、登录、首次脚本启用必须真人做（浏览器安全机制）。
- **正确做法**：xe_doctor.py 全 PASS + tabbit-ops.md 人工步骤清单完成后才进 Phase 2。
- **反模式**：试图代点浏览器安全确认，或让人自己摸索装扩展。
- **来源**：wh-xiaoetong-transcript golden_rules 规则 6。

## 规则 7：命名与下载解耦，不走猫抓标签页标题链（2026-09-03 新增）

- **内容**：猫抓命名链 = 条目 name（URL 末段，blob 时为 uuid，不可控）→ title（chrome.tabs.get 实时标签页标题）→ TitleName 模板。批量场景下该链路时序脆弱（tab 切换、标题恢复时机），且 catCatchAddMedia 协议根本不支持 name 字段（源码查证）。
- **正确做法**：油猴脚本把 {video_id, 真实标题, m3u8 文本, 解密密钥} 结构化 POST 给本地采集服务器；下载产物以 video_id 命名，organize 阶段才换成真实标题。猫抓只作手动救急支线。
- **反模式**：改 document.title 后发 catCatchAddMedia 指望文件名正确（v0.20 脚本的取巧设计，批量不可靠）。
- **来源**：cat-catch 2.7.2 源码查证（background.js/content-script.js/m3u8.js/init.js，2026-09-03）。

## 规则 8：DRM 密钥优先"直取不加工"（2026-09-03 修正：原 XOR 结论作废）

- **内容**：v-vod-k drm m3u8 的密钥接口【直接 GET 响应体即为 16 字节 AES key】（本课程实测为 ASCII 串），
  无需加 &uid、无需与 user_id XOR。XOR 变体（mz 脚本逻辑）只适用于部分部署，对本课程会得到错误 key 导致解密全乱。
- **正确做法（实测通）**：pyts 引擎逐节 GET KEY URI 原文 → 响应字节写 key.bin → AES-128-CBC 逐分片解密
  （IV 取 m3u8 IV=0x 值左补 16 字节，无则用分片序号）→ 拼接 all.ts → ffmpeg remux mp4。
- **反模式**：盲目沿用"&uid + XOR"；把原始分片直接喂 ffmpeg（分段请求带重复 sign 会 200-非 TS）。
- **来源**：2026-09-03 实跑破解（seg0 解密 TS 同步 414/414）；猫抓 m3u8.js fetch(decryptdata.uri) 同款。

## 规则 9：签名时效窗口（2026-09-03 新增）

- **内容**：m3u8 URL 与 ts 地址带 sign/t/us 防盗链参数，过期即 403。
- **正确做法**：采集完成后 2 小时内完成对应课时下载；批量跨天时按天"采集一批 → 立即下载一批"。
- **反模式**：周五采集周一下载，全军覆没 403。
- **来源**：download-recipes.md "带签名，过期失效"；本技能 Phase 3 门禁。

## 规则 10：写后必须底层复核（2026-09-03 新增）

- **内容**：Edit/Write 工具报成功但磁盘可能静默未变（本会话实测 5 连失败 + 1 次部分失败）。
- **正确做法**：每次编辑落盘后立即 grep/Read 复核关键串；失败改用 Python 全量替换。
- **反模式**：只信工具返回就声称"已修复"。
- **来源**：2026-09-03 本会话 Edit 静默失败实录；negative-results.md 负结果 5。

## 规则 11：tabbit 持久模式四大坑（2026-09-03 新增）

- **内容**：①不能管道一行连喂多帧（要等每帧回执，否则 INVALID_PERSISTENT_INPUT）；②复用已锁定的 task 名会卡死；③pages().map() 返回 Promise 不能直接 clone；④bootstrap 只绑当前事件循环的 page，接管已开标签页要传 claimTabIds。
- **正确做法**：单帧单回执；task 名带时间戳；结果在 code 块内 await 后 return 纯数据；`{"op":"tabs"}` 先盘点再 claim。
- **反模式：** printf 两帧连发 + 复用 xe-batch 任务名 + clone pages 数组。
- **来源**：2026-09-03 tabbit 实战（mutual/projects/proj-1783419177096-s8i97h work-logs）。

## 规则 12：目录结构契约——每节一个子文件夹，md 与 mp4 同名同置（2026-09-03 新增）

- **内容**：课程根文件夹内按章节建子文件夹，每个课时一个同名子文件夹，内含 `{标题}.md` + `{标题}.mp4`；课程根另有一份索引 md。
- **正确做法**：organize 阶段是唯一命名点；Obsidian 同步只做"归档旧版 + 整树复制 + 文件数校验"，不改动任何文件名。
- **反模式**：md 集中一个文件夹、mp4 集中另一个文件夹（Obsidian 双链断裂）；直接覆盖已有课程目录。
- **来源**：用户需求（2026-09-03）；结构参考 wh-xiaoetong-transcript 包组织方式。
