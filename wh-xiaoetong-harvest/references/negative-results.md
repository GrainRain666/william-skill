# 负结果归档（死路，禁止重踩）

> 本技能存在的根因：自研方向是结构墙。任何会话遇到“要不要自研小鹅通逆向”必须先读本文件。
> 负结果 1-2 继承自 wh-xiaoetong-transcript 社区包（2026-08-31 ~ 09-02），3-5 为 2026-09-03 批量化改造新增。

---

## 负结果 1：自研 Electron API 逆向（v1~v5）

- **日期**：2026-08-31 ~ 09-01
- **方案**：Electron 内页面渲染 + executeJavaScript + net.fetch API 直连 + CDP 抓包，逆向回放 m3u8 地址
- **失败**：v1 不带登录 cookie → 11302 未登录；v2 页面上下文 fetch → resource_id 为空；v3 选第一个视频 → alive_play 直播流；v4 全 body 落盘 → 全是 liveplay-byte 直播流无点播地址；v5 CDP 抓包 → 前端 JS 崩溃无干净回放地址
- **根因**：回放地址 = 登录态 + 签名 + 播放器运行时二次请求，刻意反爬设计（anti_screen_capture、forbid_record=1）
- **退出判据**：外部已有成熟方案 + 自研连续 5 轮失败 = 结构墙（工程法则 9），停手换方向
- **正确做法**：前端拦截——油猴 hook + 浏览器运行时抓真实 m3u8

## 负结果 2：AI 自动反查课程真实标题（2026-09-02）

- **方案**：连 Chrome 登录态 / 内置浏览器 / 商品详情目录 API，用 video ID 反查真实标题
- **失败**：扩展未配对；目录“购买后查看”需登录；API 试 5 种参数名全报“商品ID 必填”
- **根因**：video ID（CDN 层）与课程目录（业务层）两套体系无公开映射；登录态是浏览器私有状态
- **正确做法**：批量场景由目录页 JSON 采集真实标题（本技能 collectCourseItems 已实现）；单节无标题时用推断名 + 【待核对】

## 负结果 3：依赖猫抓标签页标题链给 mp4 命名（2026-09-03）

- **方案**：顶层先改 document.title 为章节名，再发 catCatchAddMedia，指望猫抓 TitleName 模板 `${title}.${ext}` 命名
- **失败机理**（cat-catch 2.7.2 源码查证）：
  - 条目 name = `new URL(url).pathname` 末段——blob URL 时是 uuid，**不可控**
  - `catCatchAddMedia` 协议**不支持 name 字段**（只转发 url/href/ext/mime/referer/requestId）
  - title 由 background `chrome.tabs.get(tabId)` 实时读取——tab 切换即漂移，批量时序脆弱
  - 文件名三级优先级 customFilename 输入框 > filename 参数 > title 参数（需 G.TitleName 开启），任何一环断开就回落 uuid
- **结论**：该链路只可单节救急，批量必须走清单命名（本技能规则 7）
- **正确做法**：m3u8 文本 + 真实标题 + 密钥结构化 POST 给本地服务器，organize 阶段统一命名

## 负结果 4：本机无 N_m3u8DL-RE（2026-09-03）

- **事实**：Everything 全盘检索 `N_m3u8DL-RE` 零结果；社区包的 `downloader/N_m3u8DL-RE/N_m3u8DL-RE.exe` 在另一台机器（William）
- **影响**：社区包下载命令不可直接复用
- **正确做法**：默认引擎 ffmpeg（8.1.1 WinGet 已装，HLS + AES-128 + 本地 key 文件实测可解密）；N_m3u8DL-RE 保留为 `--engine nre` 可选项

## 负结果 5：Edit/Write 工具静默失败（2026-09-03，跨会话复现两次）

- **现象**：Edit 报 "Successfully edited" 但磁盘未变（5 连失败 + 1 次部分失败：同批两处编辑一处落盘一处未落）
- **危害**：脚本带病运行；grep 复核才发现
- **正确做法**：每次编辑后立即 grep/Read 复核关键串；失败改用 Python 全量替换；写后不验证 = 禁止声称完成


## 负结果 6（已破解 2026-09-03 17:35）：v-vod-k DRM 分片“看似不可解”

- **现象**：课程 drm/main.m3u8 分片经 ffmpeg、pyts（urllib 带 Referer/UA 成功下载 588/588）+ pycryptodome AES-128-CBC（dec/zero key × 显式零 IV（KEYLINE IV=0x00000000）/序号 IV × 0-64 偏移）均无法得到 TS 0x47 同步网格（414 格 0 命中）→ 定制 DRM 负载。
- **为什么看起来可行**：密钥经 uid 异或还原链路与 mz 脚本一致、分段能下、KEYLINE 有标准 IV 字段。
- **为什么无效**：负载非标准 AES-128-HLS（TS）；仅猫抓扩展内置下载器实测可解（<YOUR_TABBIT_DIR> 的 main*.mp4 即其产物）。
- **正确做法**：下载一律交给猫抓（用户手动点，或经其扩展 Web Application 目录 `Tabbit User Data\Default\Web Applications\_crx_infppggnoaenmfagbfknfkancpbljcca` 模拟点击）；pipeline 只做采集/改名/整理/同步，禁止再走自研解密。

## 负结果 7：TM 脚本同 name 更新不可信 + __xeHarvest.version 硬编码误导（2026-09-03）

- **现象**：dashboard 显示最后更新 2026/9/3 14:54（v1.00），用户装 v1.01/1.02 后页内行为不变；页内 __xeHarvest.version 恒为 1.00（脚本内硬编码，非实际版本）。
- **正确做法**：以页内行为探测（__xeHarvest.items()>0 / 服务器是否收包）判定脚本是否生效；让用户在 TM 先删除旧脚本再安装新版；升级脚本时同步升版 version 常量。


> 更新 2026-09-03 17:35：负结果 6 已破解。根因不是定制 DRM，而是【密钥取得方式错误】——
> 一直按 mz 脚本加 &uid + XOR，实际应直取 KEY URI 响应体作 AES key（IV 用 m3u8 显式 0x00000000）。
> 破解后 seg0 解密 TS 0x47 同步 414/414，首节 mp4 时长 1174.19s 与目录 video_length 1174 一致。
> pyts 引擎 + 直取密钥 = 全自动下载通道；猫抓不再是唯一解。详见 golden_rules 规则 8。
