---
name: wh-xiaoetong-transcript
version: 1.0
description: >
  小鹅通直播回放下载转写流水线——从【猫抓复制的 m3u8 + 播放页标题】到【桌面简体逐字稿】一站式。
  同时支持【已下好的 mp4 直接转写】支线，以及新人【全流程环境复刻】（setup_env 自动装依赖 + 精确指引人工 5 步）。
  原理：下载走 N_m3u8DL-RE（带 Referer 防盗链），转写走 faster-whisper large-v3（GPU）+ opencc 繁转简，命名走真实标题优先铁律。
  触发词：转写小鹅通/小鹅通下载/小鹅通转写/猫抓链接/m3u8转写/回放转写/小鹅通视频转文字/视频转逐字稿/小鹅通逐字稿/猫抓m3u8/直播回放下载/课程回放转写/油猴猫抓转写/xiaoe transcript/小鹅通mp4转写/wh-xiaoe-transcript
---

## [LIGHTNING] 执行协议（强制 - 禁止跳过）

> **本段是执行约束，不是参考建议。违反 = 产出质量不可信。**

### [RED] 必读（执行前必须读取，不可跳过）

- 执行前**必须** `Read references/download-recipes.md` - 不读 = 不了解下载核心方法论 = 产出不合格

### [YELLOW] 按需（匹配场景时必须读取）

- 场景[新人/环境没配过] -> **必须** `Read references/env-setup.md`
- 场景[浏览器扩展相关] -> **必须** `Read references/browser-ext-setup.md`
- 场景[要命名交付] -> **必须** `Read references/naming-rules.md`
- 场景[报错/环境异常] -> **必须** `Read references/troubleshooting.md`
- 场景[要不要走自研逆向] -> **必须** `Read references/negative-results.md`

### [STOP] 门禁

- Phase 执行前：确认已读取 references/download-recipes.md。未读 -> **禁止继续**
- 输出结论前：确认有 evidence path (Source: path#line)。无证据 -> **禁止声称**
- 命名交付前：确认文件名不含"推断名但未标注【待核对】"。未标注 -> **禁止交付**
- 跳过本协议 = 违反工程法则 8（门禁不可跳过）

---

# wh-xiaoetong-transcript：小鹅通回放 → 桌面简体逐字稿

> 半自动流水线：抓 m3u8 那步必须人在浏览器点（安全边界，谁都替代不了），skill 管剩下全自动的 80%。

## 设计哲学（5 条）

1. **前端拦截优于后端逆向**：小鹅通回放地址 = 登录态 + 签名 + 播放器运行时二次请求，自研 API 逆向是结构墙（5 轮验证失败）。用油猴脚本 + 猫抓在浏览器运行时抓真实 m3u8，天然带签名。
2. **环境配置是一等模块**：给新人能完全复刻的流程——自动装 85%，精确指引必须人工的 15%（浏览器扩展是安全机制）。
3. **命名必须真实标题**：下载后必须与用户给的课程标题核对再定文件名，推断名强制标注【待核对】。
4. **防重复下载**：m3u8 到手先查 video ID + 分片时长 + 音频指纹，同视频绝不重复转写。
5. **脚本黑盒化**：scripts/ 是黑盒工具，用 `--help` 调用，不读源码（li-webtest 模式）。

## 理论锚点

| # | 理论 | 应用 | 来源 |
|---|------|------|------|
| T1 | 结构墙 | 自研逆向 5 轮失败 = 换方向，不是再试 1 次 | 工程法则 9 |
| T2 | 认知负荷理论 | 主文件≤300行，细节在 references/ | 《为什么学生不喜欢上学》 |
| T3 | 反脆弱 | 负结果归档，死路不被后续会话重踩 | 《反脆弱》 |
| T4 | 损失厌恶 | 改文件名前先归档，可随时回退 | 《思考，快与慢》 |
| T5 | 路径依赖 | 命名/路径一旦错，后续全错——命名铁律 | 路径依赖理论 |

## Phase 0：输入消解（3 秒）

```
用户输入分类：
  ├─ "转写这个 m3u8: xxx，标题 yyy" → 模式 A：下载 + 转写
  ├─ "转写这个 mp4: xxx，标题 yyy"  → 模式 B：直转（跳过下载）
  ├─ "配置环境 / 新人复刻 / 环境没配" → Phase 1 setup_env
  ├─ "检查环境" → verify_env.py
  └─ 输入不完整（缺标题）→ 先按内容推断名标注【待核对】交付，同时提醒用户补真实标题
```

**铁律**：m3u8 地址必须配播放页标题一起用（真实标题优先）；只有地址没有标题时，允许用转写内容推断命名，但文件名必须带【待核对】标记。

## Phase 1：环境就绪（新人 / 报错时）

1. 跑 `python scripts/setup_env.py`（自动：装依赖 + GPU 修复 + 就位下载器 + 输出 `人工步骤清单.md`）
2. 跑 `python scripts/verify_env.py`（PASS/FAIL 清单，FAIL 项给出修复动作）
3. 人工段（只能真人做）：装 Tampermonkey + 猫抓扩展 → 装油猴脚本 → 登录小鹅通 → 播放页抓 m3u8
4. 全 PASS + 人工 5 步完成 → 进入 Phase 2

> 详细步骤 → `references/env-setup.md`（自动步骤）+ `references/browser-ext-setup.md`（人工步骤全细节）

## Phase 2：下载（模式 A）

1. **防重复判定**：从 m3u8 提取 video ID（URL 路径中 `/{id}vodcq/` 段），与 `downloads/` 已有文件对比；video ID 相同 → 拒绝下载并说明（可能是同视频新签名）
2. 用 N_m3u8DL-RE 下载：
   ```bash
   ./downloader/N_m3u8DL-RE/N_m3u8DL-RE.exe "<m3u8>" \
     --save-dir "downloads/_tmp" \
     -H "Referer: https://YOUR_XIAOETONG_HOST/" \
     -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)" \
     --thread-count 16
   ```
3. 校验产物：ffprobe 时长/分辨率/大小，确认是新视频（时长与上节不同）
4. 无 `#EXT-X-KEY` = 无加密直接合并；有则 N_m3u8DL-RE 自动解密

> 命令模板与参数说明 → `references/download-recipes.md`

## Phase 3：转写（large-v3 + GPU + 繁转简）

```bash
python scripts/xiaoetong_transcript.py "<mp4>" --model large-v3 --out "transcripts/.tmp.md"
```

- GPU（cuda/float16）约 7 分钟/90 分钟视频；CPU 慢 20 倍，先跑 `verify_env.py` 确认 GPU 就绪
- 脚本内置 opencc 繁转简（简体输出），VAD 过滤静音，段落合并 = 静音>1s + 句末标点
- 转写完抽验 1-2 段内容质量，确认与标题主题吻合

## Phase 4：命名与交付（命名铁律）

1. **真实标题优先**：用户给的播放页标题（document.title）就是真实课程名
2. **推断名必须标注**：没有真实标题时，用转写内容 + m3u8 转码时间推断，文件名带【待核对】，交付时明确告知
3. 命名格式：`{序号}.{YYYY.M.D}-{标题去省略号}.md` / `.mp4`
4. 交付：桌面 `<YOUR_DESKTOP>\{标题}-逐字稿.md` + 工作区 `transcripts/` + `downloads/`
5. 改名前先归档旧文件到 `<YOUR_ARCHIVE_DIR>\{日期}-逐字稿更名`

> 命名细则与省略号处理 → `references/naming-rules.md`

## Phase 5：记录与生态

1. 更新 `README-油猴猫抓下载方案.md` 的【已验证】章节（追加本次交付）
2. 追加 `memory/{今日}.md`（下载/转写耗时、video ID、标题来源）
3. 联动检查：是否需要 li-sync / li-improve（见联动技能）

## 反模式（速查）

| # | 反模式 | 为什么不行 | 正确做法 |
|---|--------|-----------|---------|
| 1 | 自研逆向 API（Electron/CDP） | 结构墙，5 轮失败 | 前端拦截（油猴+猫抓）或成熟下载器 |
| 2 | 凭印象命名不核对标题 | 52 节更名事故 | 真实标题优先，推断名标【待核对】 |
| 3 | 同 video ID 重复下载转写 | 浪费 1.6GB + 几小时 | 先查 ID + 时长 + 音频指纹 |
| 4 | 环境缺 GPU DLL 硬跑 CPU | 82 分钟视频要 2-4 小时 | verify_env 先修 cublas，走 GPU |
| 5 | 让用户反复手动重启/贴日志 | 试错成本押用户身上 | 一次性拿全证据链再动手 |

## 案例库（→ 详见 references/download-recipes.md § 实战记录）

- **案例 1（52 节）**：2026-09-01 首节全链路跑通，发现 GPU（RTX 5070 Ti）闲置并修复 cublas DLL；命名失误（凭印象起名）后被用户更正 → 沉淀命名铁律
- **案例 2（51 节）**：102 分钟视频 large-v3 转写 658 秒，标题先推断后更正 → 沉淀【播放页标题就是真实标题】规则
- **案例 3（53 节）**：90 分钟视频 454 秒，video ID 判定防重复；用户给的标题带省略号 → 沉淀省略号处理

## 决策路由表

| 主题 | 路由文件 | 说明 |
|------|----------|------|
| 环境自动搭建/GPU 修复 | `references/env-setup.md` | setup_env.py 行为 + cublas 复制法 |
| 浏览器扩展人工步骤/manifest 修复 | `references/browser-ext-setup.md` | Tampermonkey/猫抓/Tabbit/权限清理 |
| 下载命令/防重复/加密判定 | `references/download-recipes.md` | N_m3u8DL-RE 全参数 + video ID 识别 |
| 命名规则/待核对标注 | `references/naming-rules.md` | 真实标题优先/省略号/归档 |
| 报错排查 | `references/troubleshooting.md` | cublas/torch CPU/manifest/OCR |
| 死路归档 | `references/negative-results.md` | 自研 v1-v5 + 结构墙判据 |

## 联动技能

| Skill | 触发条件 | 联动方式 |
|-------|---------|---------|
| li-transcript | 逐字稿需道法术器拆解 | 转写完成后调用，输出拆解版 |
| li-analyze | 需要深度分析课程内容 | 逐字稿 → 道法术器 |
| li-memory | 逐字稿有可沉淀事实 | 提取关键知识入记忆 |
| li-improve | 用户对输出不满/新教训 | 命名失误、下载失败等沉淀规则 |
| li-sync | 修改了共享规则/README | 跨工作区同步 |

## Conditional Next Steps

| Signal | Action | Chain |
|--------|--------|-------|
| [Phase complete] | Determine next phase | Continue within this skill |
| [环境缺件] | Run setup_env.py + verify_env.py | Setup phase |
| [同视频重复] | 拒绝并说明，等新 m3u8 | Stop, wait for user |
| [标题待核对] | 交付但标注，等用户真实标题 | Rename on user confirm |
| [用户不满] | li-improve 记录教训 | Improvement phase |
| [Memory update needed] | 更新 memory/{今日}.md | Memory |

## 说话风格与禁止模式

- 结论先行 → 原因 → 引用（Source: path#line）
- 中文全角标点，禁止 emoji，用【】不用【】
- 诚实边界：只能声称已验证的（downloads 实测）；浏览器扩展安装、登录态抓包属于人工段，明说"这步必须你做"
- 禁止编造标题/时长/进度；ffprobe/落盘验证过了才说"完成"
