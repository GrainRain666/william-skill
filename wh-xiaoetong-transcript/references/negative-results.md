# 负结果归档（死路，禁止重踩）

> 本 skill 存在的根因：自研方向是结构墙，5 轮验证失败后换到前端拦截方案才跑通。
> 任何后续会话遇到【要不要自研小鹅通逆向】必须先读本文件。

---

## 负结果 1：自研 Electron API 逆向（v1~v5）

### 日期
2026-08-31 ~ 09-01（实际执行）

### 方案
不采用现成下载器，在自研 Electron 工具内通过页面渲染 + executeJavaScript + API 直连（net.fetch）+ CDP 抓包（debugger Network），逐步逆向小鹅通直播回放 m3u8 地址。

### 已尝试
- v1：net.fetch 用 default session 请求 base_info → 不带 persist:xiaoe 登录 cookie → 11302 未登录
- v2：改在页面上下文内 fetch（带分区 cookie）→ 拿到 base_info，但选中图文项 resource_id 为空
- v3：选第一个视频 → base_info 返回 alive_play（直播流地址）
- v4：完整 body 落盘 → alive_play.* 全是 liveplay-byte 直播流，recorded_use_pull_stream=false，无点播回放地址
- v5：CDP 抓包抓前端真实回放请求 → 未得到回放地址；parseWindow 被置 null 抛 webContents 错

### 失败现象
- 小鹅通新版页面 JS 在 Electron 崩溃（`Cannot use import statement outside a module`）
- base_info 只给直播流配置；回放 m3u8 由播放器运行时向另一带签名接口请求，无法手工拼出
- CDP 抓包也因前端 JS 崩溃拿不到干净回放地址

### 为什么看起来行其实不行
- 路径看似直接（登录态 → base_info → m3u8），但小鹅通回放地址是【登录态 + 签名 + 播放器运行时二次请求】刻意设计（防盗链、anti_screen_capture、forbid_record=1）
- 自研逆向 = 与平台反爬体系对抗，投入产出比极低
- 反复让用户手动重启+扫码+贴日志，试错成本全押用户身上

### 退出判据
- 外部已有成熟方案（油猴脚本 / 学无止下载器 / N_m3u8DL-RE），社区验证可用
- 自研连续 5 轮（v1~v5）未拿到回放地址 → 判定结构墙（工程法则 9），停手换方向

### 正确做法
- 小鹅通回放下载 = 前端拦截（油猴脚本【小鹅通通用m3u8获取】+ 猫抓 cat-catch）或成熟下载器（学无止下载器 PyJun/Mooc_Downloader，v2.15.13 支持小鹅通含回放）
- 拿到视频后接 faster-whisper 转写（xiaoetong_transcript.py）

### 关联法则
工程法则 9（结构墙）、法则 3（实测优先）、search-decision-tree（先找成熟方案）、think-before-act

### 影响范围
- 自研 tools/src/main.js 已删除（2026-09-01），归档到 `<YOUR_ARCHIVE_DIR>\2026-09-01-删除小鹅通自研工具`
- 不再沿 Electron API 直连解析方向

---

## 负结果 2：自动获取精确课程标题

### 日期
2026-09-02（51 节命名尝试）

### 方案
AI 自主从商品详情 API 反查课程目录，匹配 video ID 得真实标题。

### 已尝试
- 连用户 Chrome（登录态）→ 失败（扩展未配对）
- 内置浏览器打开课程页 → 目录【购买后查看全部课程】需登录，不可见
- 调商品详情目录 API → 试 5 种参数名全报【商品ID 为必填项】，参数名未知

### 失败现象
登录态不可得 + API 参数名未知，无法自动匹配 video ID → 真实标题。

### 为什么看起来行其实不行
- video ID（CDN 层）与课程目录（业务层）是两套体系，无公开映射
- 登录态是浏览器私有状态，AI 无法稳定获取

### 退出判据
尝试 ≥3 种独立方法失败 → 停止自动获取，用【推断名+【待核对】】交付，请用户提供播放页标题。

### 正确做法
用户在浏览器打开播放页时，页面标签标题（document.title）就是真实标题。让用户顺手复制，AI 用它命名。
