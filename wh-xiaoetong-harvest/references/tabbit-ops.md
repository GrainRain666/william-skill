# tabbit-ops — tabbit 浏览器操控与脚本安装（必读）

> tabbit 提供小鹅通登录态（2026-09-03 实测有效）。本文件 = tabbit-cli 协议 + 已验证的坑 + 脚本一次性安装 + 三条备选轨道。

## 一、tabbit-cli 协议（已验证）

```
launcher = <YOUR_USER_DIR>\AppData\Local\Tabbit\LocalAgent\bin\tabbit-cli.exe
实例注册表 = <YOUR_USER_DIR>\AppData\Local\Tabbit\LocalAgent\instances\A407798DAD62710E.json
```

标准帧流（每帧等回执，禁止管道连喂多帧）：

```bash
printf '{"op":"tabs"}' | "tabbit-cli.exe" persistent        # 盘点全量标签页（NDJSON）
printf '{"op":"bootstrap","taskName":"xe-harvest-1400","requestId":"q1","claimTabIds":[<tabId>],"code":"return await page.title();"}' | "tabbit-cli.exe" persistent
printf '{"op":"run","requestId":"q2","code":"await page.goto(\"<课程目录页URL>\",{waitUntil:\"domcontentloaded\"}); await page.waitForTimeout(5000); return document.title;"}' | "tabbit-cli.exe" persistent
printf '{"op":"finish"}' | "tabbit-cli.exe" persistent       # 收尾恰好一次；保留标签页
```

- `code` 里是 Playwright 语句；返回值必须 await 后 return **纯数据**（`pages().map(...)` 返回 Promise 不能 clone）
- `queued` 回执 → `{"op":"inspect","requestId":"同id","waitMs":60000}` 等待，**禁止重发**
- 持久模式复用已锁定 task 名会卡死；task 名带时间戳。卡死备选：`tabbit-cli.exe nodejs --task <新名>` 兼容命令单次执行
- bootstrap 只绑当前事件循环的 page；接管已开标签页必须 `{"op":"tabs"}` 盘点后传 `claimTabIds`

## 二、油猴脚本一次性安装（人工段，唯一需要真人做的步骤）

1. tabbit 地址栏 `tabbit://extensions` → 开【开发者模式】（若被隐藏：Chrome 装好后走"从 Chrome 迁移扩展"）
2. 确认已装：篡改猴（Tampermonkey）+ 猫抓（cat-catch）；没有则从应用商店装
3. 安装采集脚本（避开 file:// 拦截，本地 http 托管）：
   ```bash
   cd "<YOUR_USER_DIR>\.workbuddy\skills\wh-xiaoetong-harvest\scripts\userscript"
   python -m http.server 8543 --bind 127.0.0.1
   ```
   浏览器访问 `http://127.0.0.1:8543/小鹅通课程批量采集器.user.js` → 篡改猴弹安装页 → 点【安装】
4. 验证：打开小鹅通课程目录页 → 篡改猴图标出现红色角标；脚本自动开始批量采集（右下角有提示条）
5. 配置热更（控制台执行）：
   `localStorage.setItem('xeHarvestCfg', JSON.stringify({server:"http://127.0.0.1:8771", enabled:true, auto:true}))`

## 三、AI 驱动采集的标准流程（主轨道）

```bash
# 终端 1：采集服务器
python scripts/xe_server.py --port 8771 --workdir "<工作目录>/xiaoe-harvest"

# 终端 2：AI 逐帧驱动 tabbit
{"op":"tabs"}                                        # 盘点，找已登录的小鹅通标签页
{"op":"bootstrap",...,"claimTabIds":[<id>],"code":"await page.goto('<目录页URL>',{waitUntil:'domcontentloaded'}); return page.url;"}
# 脚本自动：收集目录 → 4 秒去抖 → 后台串行 iframe 抓取 → POST 服务器
# AI 侧轮询（每 30 秒）：
curl http://127.0.0.1:8771/status
# 连续 2 分钟 lessons/keyed 不变 = 完成；与目录页节数比对，缺节重开对应课程页补采
```

- 模式 A（全课程）：先开 learnIndex 主页让脚本上报 course_list，再逐门打开课程目录页
- 模式 C（单节）：直接开播放页，脚本原版逻辑兼容

## 四、备选轨道（优先级从高到低）

### 轨道 2：tabbit 内直接注入采集 JS（免装脚本）

bootstrap/run 的 `code` 里注入与油猴脚本同逻辑的 hook（JSON.parse/XHR/indexOf + video_urls 解码），
挂到 `window.__xeCapture` 缓冲，`{"op":"run",...,"code":"return window.__xeCapture;"}` 收取。
适合：篡改猴不可用/脚本未装的应急。缺点：跨页状态难维持，逐节注入慢。

### 轨道 3：playwright 接管登录态

```python
# chromium 持久化 profile 指向 tabbit 用户数据目录不可行（被占用），改用：
# 1) tabbit --remote-debugging-port=9222 启动（或实例注册表里已开的调试口）
# 2) playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
# 3) 复用轨道 2 的注入逻辑逐页驱动
```

适合：需要无人值守长跑。注意：连接前先确认调试口已开、不与 tabbit-cli 抢同一 page。

### 轨道 4：猫抓手动支线（救急）

油猴脚本仍会向猫抓投递（postMessage 桥）。人工在猫抓弹窗里全选下载。文件名不保证正确
（见 negative-results.md 负结果 3），下载后需按清单手工改名——只用于单节救急。

## 五、常见故障

| 现象 | 根因 | 处置 |
|------|------|------|
| INVALID_PERSISTENT_INPUT | 管道连喂多帧 | 单帧单回执 |
| 持久模式卡死/超时 | task 名复用 | 换带时间戳的新 task 名 |
| could not be cloned | clone 了 Promise | code 内 await 后 return 纯数据 |
| 采集数 < 目录节数 | 目录未滚动加载完 | 滚动到底后等去抖重采；或重开课程页 |
| captured 有数 keyed 不涨 | 密钥接口没触发 | 回对应播放页重开一次 |
