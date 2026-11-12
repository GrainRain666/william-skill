# structure-spec — 目录结构契约与命名规则（必读）

> organize 阶段是唯一命名点。本文件定义课程根文件夹的完整结构契约、md 模板与命名清洗规则。

## 一、目标结构（以“你的课程名”为例）

```
~/Documents/Xiaoetong\
└── 你的课程名\              # 课程根 = root_name
    ├── 你的课程名.md        # 课程索引（自动生成）
    ├── 第2章\                       # 章节层
    │   ├── 2-1顶刊学问2\            # 课时层 = 每节一个同名子文件夹
    │   │   ├── 2-1顶刊学问2.md      # 逐字稿/笔记（与 mp4 同名同置）
    │   │   └── 2-1顶刊学问2.mp4
    │   └── 2-2顶刊量化方法1\...
    ├── 第5章\
    │   └── 5-1风口概论1\...
    └── 正文\                        # 无章节信息的课时兜底归此
```

- 章节层命名优先级：采集清单 chapter 字段（目录页真实章节名）> 标题序号推断（`5-1xxx` / `5.1xxx` / `5、xxx` → 第5章）> 【正文】
- 课时层命名 = 采集清单 title（目录页显示名，未经改动）
- 同章节下同名课时冲突 → 后者加 ` -2`、` -3` 后缀，绝不静默覆盖

## 二、课时 md 模板（Obsidian 友好）

```markdown
---
course: 你的课程名
chapter: 第2章
title: 2-1顶刊学问2
video_id: v_EXAMPLE_LESSON_ID
source: https://APP_YOUR_ID.h5.xet.pomoho.com/p/course/video/v_...
captured_at: 2026-09-03 14:00:00
downloaded_at: 2026-09-03 14:10:00
duration_seconds: 4948.8
size_bytes: 1593474428
status: 待转写
---

# 2-1顶刊学问2

> 所属课程：你的课程名
> 章节：第2章
> 视频文件：[2-1顶刊学问2.mp4](2-1顶刊学问2.mp4)（与本文档同目录）

## 逐字稿

【待转写】运行 transcribe 阶段后，此处替换为段落级时间戳逐字稿
（faster-whisper large-v3 GPU，opencc 繁转简，段落=静音>1s 且句末标点）。
```

- status 取值：`待转写` / `已转写`；已转写时【待转写】占位整段替换为逐字稿正文（取转写产物 `## 逐字稿` 之后的内容）

## 三、课程索引 md（root_name.md，自动生成）

```markdown
# 你的课程名

> 来源：小鹅通课程 {course_id} ｜ 由 wh-xiaoetong-harvest 生成于 {时间}
> 共 {n} 节：{keyed} 节带密钥，{downloaded} 节已下载

## 章节

- [第2章](./第2章/)
  - [2-1顶刊学问2](./第2章/2-1顶刊学问2/2-1顶刊学问2.md)
  - ...
```

## 四、命名清洗规则（safe_title）

1. 删除结尾省略号 `…` / `...`
2. 删除 Windows 非法字符 `\ / : * ? " < > |`
3. 压缩连续空白为单空格，首尾去空白
4. 长度截断到 80 字符（保留前 80）
5. 清洗后为空 → 回退 video_id 命名并【待核对】标注

## 五、root_name 决策顺序

```
--root-name 显式指定
  > state.courses[course_id].course_title（课程页采集）
  > 多数课时共有的 course_title（iframe 透传）
  > course_id
  > "小鹅通课程"
```

已知课程“你的课程名”建议显式 `--root-name "你的课程名"`，防止页面标题带后缀噪声。

## 六、Obsidian 同步规则

- 目标 = `--obsidian-vault`（默认 `~/Documents/Xiaoetong`）+ root_name
- **先归档再修改**：目标已存在 → 整树移入 `<YOUR_ARCHIVE_DIR>\{YYYYMMDD-HHMM}-xiaoe-harvest-obsidian\{root_name}`，再复制新版
- 复制后校验：源与目标的 md 数、mp4 数逐一相等，不等即 fail（打印差集）
- vault 根是 `~/Documents`（.obsidian 在该层），`小鹅通` 是库内一个分区文件夹
