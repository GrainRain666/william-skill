---
name: wh-xiaoetong-harvest
version: 1.0
description: >
  小鹅通课程一键批量下载与知识库入库。输入用户学习主页 URL（study.xiaoe-tech.com/t_l/learnIndex#/muti_index）
  或课程目录页 URL，自动枚举全部课程与章节课时，采集每节 m3u8 + AES-128 解密密钥 + 真实标题，
  ffmpeg 解密合并 mp4；按【课程根文件夹/章节/课时】建立子文件夹，每节同时含逐字稿 md 与 mp4；
  先归档再同步进 Obsidian 仓库（默认 ~/Documents/Xiaoetong）。
  浏览器优先 tabbit（AI 操控篡改猴脚本 + 猫抓桥接），playwright 备选；下载引擎 ffmpeg，N_m3u8DL-RE 可选。
  触发词：小鹅通批量下载/批量下载课程/一键下载课程/课程打包下载/小鹅通课程下载/批量抓取课程/
  小鹅通知识库/课程入库/课程批量下载/小鹅通所有课程/小鹅通mp4批量/Obsidian课程库/xiaoe harvest/小鹅通harvest
---

## 执行协议（强制 - 禁止跳过）

> 本段是执行约束，不是参考建议。违反 = 产出质量不可信。

### 必读（执行前必须读取）

- 采集与下载前 **必须** `Read references/xe-data-chain.md` —— 不读 = 不了解 m3u8/密钥/防重复链路 = 禁止继续
- 浏览器操控前 **必须** `Read references/tabbit-ops.md`
- 整理与命名前 **必须** `Read references/structure-spec.md`

### 门禁

- 修改/覆盖任何已有文件（含 Obsidian 仓库内容）前：**先归档**（obsidian 阶段内置自动归档；手工操作先复制到 `<YOUR_ARCHIVE_DIR>`）
- 命名交付前：文件名必须来自采集清单真实标题；推断名必须带【待核对】
- 声称完成前：文件必须已落盘并用 ls/ffprobe/grep 验证过；未验证 = 禁止声称
- 写入后的文件必须用底层命令（grep/Read）复核——Edit/Write 工具可能静默失败（见 negative-results.md）

## 设计哲学（6 条）

1. **前端拦截优于后端逆向**：小鹅通回放地址 = 登录态 + 签名 + 播放器运行时二次请求，自研 API 逆向是结构墙（5 轮验证失败）。浏览器运行时抓真实 m3u8，天然带签名。
2. **命名与下载解耦**：下载产物以 video_id 命名，最终文件名在 organize 阶段由采集清单的真实标题决定——不依赖猫抓"标签页标题"命名链（该链路 name=URL 末段不可控，批量必乱）。
3. **密钥在页面侧解密**：AES-128 密钥与 user_id 字节异或存储，ffmpeg/N_m3u8DL-RE 都不认；油猴脚本按原版逻辑异或还原后上报，流水线把 m3u8 的 KEY URI 改写为本地 key.bin。
4. **先归档再修改**：Obsidian 同步阶段若目标已存在，先整体移入归档目录再复制新版；任何手工改动同样遵守。
5. **防重复下载**：m3u8 到手先查 CDN 层 video ID（`/{id}vodcq/` 段或路径倒数第二段），同视频新签名拒绝重复下载。
6. **脚本黑盒化**：scripts/ 用命令行调用不读源码；本 SKILL.md 只管编排，细节在 references/。

## 链路总览

```
tabbit 浏览器（登录态）
  └─ 篡改猴【小鹅通课程批量采集器】user.js
       ├─ hook JSON.parse / XHR / indexOf → 抓 video_urls → base64 解码 → 拼真实 ts 地址
       ├─ 目录页收集 章节/课时/标题 → 后台串行 iframe 打开播放页
       ├─ 密钥接口 &uid= → 与 user_id 异或还原
       ├─ POST http://127.0.0.1:8771/ingest  → xe_server.py 落盘 state.json + raw/
       └─ （兼容桥）postMessage 猫抓 catCatchAddMedia/Key → 猫抓手动下载支线
xe_pipeline.py
  ├─ download   m3u8 改写 KEY URI → ffmpeg 解密合并 mp4 → ffprobe 验证
  ├─ organize   课程根/章节/课时 子文件夹，每节 {标题}.md + {标题}.mp4
  ├─ obsidian   先归档旧版 → 复制进 ~/Documents/Xiaoetong\{课程根} → 文件数校验
  └─ transcribe 可选：faster-whisper large-v3 GPU 逐字稿回填 md
```

## Phase 0：输入消解（3 秒）

```
用户输入分类：
  ├─ 学习主页 learnIndex URL → 模式 A：全课程批量（先采集课程清单，再逐门课程）
  ├─ 课程目录页 /p/course/ecourse/ URL → 模式 B：单课程批量
  ├─ 单视频播放页 /p/course/video/ URL → 模式 C：单节（原版逻辑兼容，采集后同样走流水线）
  ├─ "继续上次" → 读 workdir/state.json 断点续跑
  └─ 缺 URL → 请用户提供，禁止凭记忆编造课程链接
```

## Phase 1：环境就绪

```bash
python scripts/xe_doctor.py
```

全 PASS 才进入 Phase 2。WARN 项按提示决定是否继续（N_m3u8DL-RE 缺失可忽略，默认引擎 ffmpeg）。

## Phase 2：采集（浏览器端）

1. 启动采集服务器（保持运行）：
   ```bash
   python scripts/xe_server.py --port 8771 --workdir "<工作目录>/xiaoe-harvest"
   ```
2. 油猴脚本首次安装（人工一次性步骤）→ `references/tabbit-ops.md` 第二节
3. AI 驱动 tabbit 打开课程目录页（模式 B）或学习主页（模式 A）→ 脚本自动收集并后台串行抓取
4. 轮询监控直到数量稳定：
   ```bash
   curl http://127.0.0.1:8771/status
   ```
   连续 2 分钟 lessons/keyed 数量不变 = 采集完成；对比目录页节数，缺哪些补哪些（重开对应课程页）
5. 密钥缺失（captured 但未 keyed）的课：回该课播放页重开一次让密钥接口再触发

备选轨道（优先级从高到低）：
- tabbit 内直接注入采集 JS（免装脚本）→ `references/tabbit-ops.md` 第三节
- 猫抓手动支线：脚本仍会向猫抓投递，人工在猫抓里下载单节救急
- playwright 接管登录态浏览器逐页触发 → `references/tabbit-ops.md` 第四节

## Phase 3：下载

```bash
python scripts/xe_pipeline.py --workdir "<工作目录>/xiaoe-harvest" --stage download
```

- 引擎默认 ffmpeg（解密 + 合并一体）；`--engine nre --nre-bin <路径>` 可切换 N_m3u8DL-RE
- 防重复：CDN video ID 命中 history.json 直接拒绝（同视频新签名）
- key_missing 的课先回 Phase 2 补密钥；download_failed 看 `<vid>/tool.log` 末尾（多为 Referer/签名过期）
- 签名有时效：采集后 2 小时内完成下载，过期重开课程页重新采集该节

## Phase 4：整理（结构契约）

```bash
python scripts/xe_pipeline.py --workdir "<工作目录>/xiaoe-harvest" --stage organize \
  --root-name "你的课程名"        # 默认取采集到的课程真实标题，可显式指定
```

产物结构（完整规范 → `references/structure-spec.md`）：

```
你的课程名/
├── 你的课程名.md          # 课程索引
├── 第2章/
│   ├── 2-1顶刊学问2/
│   │   ├── 2-1顶刊学问2.md
│   │   └── 2-1顶刊学问2.mp4
│   └── 2-2顶刊量化方法1/...
```

- 章节文件夹：采集到的章节名优先；无章节元数据时从标题序号推断（`5-1xxx` → 第5章）；都没有归【正文】
- 先 `--dry-run` 预览再实跑；同名课时自动加 ` -2` 后缀，绝不静默覆盖

## Phase 5：Obsidian 同步（先归档再修改）

```bash
python scripts/xe_pipeline.py --workdir "<工作目录>/xiaoe-harvest" --stage obsidian \
  --obsidian-vault "~/Documents/Xiaoetong"
```

- 目标 `{vault}/{课程根}` 已存在 → 自动整体归档到 `<YOUR_ARCHIVE_DIR>\{时间戳}-xiaoe-harvest-obsidian\` 再复制新版
- 复制后校验 md/mp4 文件数与源一致，不一致报 fail

## Phase 6：转写（可选，重 GPU）

```bash
python scripts/xe_pipeline.py --workdir "<工作目录>/xiaoe-harvest" --stage transcribe --model large-v3
python scripts/xe_pipeline.py --workdir "<工作目录>/xiaoe-harvest" --stage organize && \
python scripts/xe_pipeline.py --workdir "<工作目录>/xiaoe-harvest" --stage obsidian
```

- GPU（cuda/float16）约 7 分钟/90 分钟视频；100 节约 12 小时 GPU 时间，建议 `--limit` 分批过夜跑
- 转写完必须重新 organize + obsidian 回填 md；未转写的 md 带【待转写】占位
- GPU 缺 DLL / CPU 慢 20 倍等问题 → 先跑 xe_doctor 的 transcribe 检查

## Phase 7：记录与收尾

1. 追加 `memory/{今日}.md`：课程名、节数、成功/失败清单、耗时
2. 失败与死路追加 `references/negative-results.md`
3. 用户不满/新教训 → 联动 li-improve

## 反模式速查

| # | 反模式 | 后果 | 正确做法 |
|---|--------|------|---------|
| 1 | 依赖猫抓标签页标题命名 mp4 | name=URL末段不可控，批量文件名全乱 | 清单真实标题在 organize 阶段统一命名 |
| 2 | 自研逆向小鹅通 API | 结构墙（5 轮失败） | 前端拦截：油猴 hook + 浏览器运行时抓取 |
| 3 | 不查 CDN video ID 直接下载 | 同视频重复浪费 GB 级流量 | history.json 双键防重 |
| 4 | 把未异或还原的密钥交给 ffmpeg | 解密出乱码视频 | 页面侧异或还原后上报，KEY URI 改写本地 key.bin |
| 5 | 采集后隔天再下载 | sign/t/us 过期 403 | 采集后 2 小时内下载；过期重采 |
| 6 | Obsidian 目标已存在直接覆盖 | 毁掉已有笔记 | obsidian 阶段先自动归档再复制 |
| 7 | 写完文件不验证 | 工具可能静默失败 | grep/Read 复核落盘 |
| 8 | 凭印象命名/推断名不标注 | 52 节更名事故重演 | 真实标题优先，推断名带【待核对】 |

## 决策路由表

| 主题 | 路由文件 |
|------|----------|
| m3u8 结构/密钥链路/服务器协议/防重复 | `references/xe-data-chain.md` |
| tabbit 操控/脚本安装/备选轨道 | `references/tabbit-ops.md` |
| 目录结构契约/命名规则/md 模板 | `references/structure-spec.md` |
| 死路与负结果 | `references/negative-results.md` |
| 命名铁律来源/防重复细节 | `golden_rules.md` |

## 联动技能

| Skill | 触发条件 | 联动方式 |
|-------|---------|---------|
| wh-xiaoetong-transcript | 单节转写/环境复刻（社区参考包，本机 tmp/wh-xiaoetong-ref 有解包） | 转写阶段脚本即源自该包 |
| li-transcript | 逐字稿需清洗/道法术器拆解 | transcribe 完成后调用 |
| li-devil | 用户问"方案稳不稳/会不会翻车" | 预验尸后再动手 |
| li-improve | 用户不满/新教训 | 规则沉淀 |
| tabbit（WorkBuddy 插件技能） | 浏览器操控 | Phase 2 主轨道 |

## Conditional Next Steps

| Signal | Action |
|--------|--------|
| [采集数量 < 目录节数] | 重开对应课程页 / 滚动加载后等去抖重采 |
| [key_missing] | 回播放页重开触发密钥接口 |
| [sign 过期 403] | 重开课程页重新采集该节再下载 |
| [同视频新签名] | 拒绝下载，人工确认后可 --video-id 强制单节处理 |
| [磁盘不足] | xe_doctor WARN 提示，先清理再批量 |
