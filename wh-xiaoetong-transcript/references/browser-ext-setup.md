# 浏览器扩展人工步骤全细节（Tampermonkey + 猫抓 + 油猴脚本）

> 本文件是 wh-xiaoetong-transcript 的环境人工段。环境全流程见 env-setup.md。
> 安全边界：扩展安装确认是浏览器安全机制设计给"真人确认"的，任何脚本/程序无法代点。

---

## 一、资产就位（setup_env.py 核验后）

| 资产 | 路径 | 用途 |
|------|------|------|
| 油猴脚本 v0.10 | `download/小鹅通-通用m3u8获取.user.js` | 运行时挂钩抓 m3u8 |
| Tampermonkey 5.5.0 | `download/extracted/tampermonkey/` | 油猴管理器（已解压目录） |
| 猫抓 2.7.2 | `download/extracted/catcatch/` | 接收 m3u8 + 下载 |
| N_m3u8DL-RE | `downloader/N_m3u8DL-RE/N_m3u8DL-RE.exe` | 命令行下载器 |

## 二、Chrome 安装（推荐，标准 Chromium）

### 步骤 1-2：加载两个扩展
1. Chrome 地址栏 `chrome://extensions` → 打开右上角【开发者模式】
2. 点【加载已解压的扩展程序】→ 选 `download/extracted/tampermonkey/`（选文件夹本身，不进入内部）
3. 再点一次 → 选 `download/extracted/catcatch/`

### 步骤 3：装油猴脚本（避开 file:// 拦截）
- **问题**：把 .user.js 拖进浏览器走 `file://` 源，Chromium 拦截【无法从该网站添加应用、扩展程序和用户脚本】
- **解法**：本地 http 服务托管
  ```bash
  cd "outputs/小鹅通转写工作流"
  python -m http.server 8543 --bind 127.0.0.1
  ```
  浏览器地址栏访问：
  `http://127.0.0.1:8543/小鹅通-通用m3u8获取.user.js`（URL 编码：`http://127.0.0.1:8543/%E5%B0%8F%E9%B9%85%E9%80%9A-%E9%80%9A%E7%94%A8m3u8%E8%8E%B7%E5%8F%96.user.js`）
- 油猴弹安装页 → 点【安装】
- 备选：Tampermonkey 图标 → 管理面板 → 实用工具 → 文件导入 → 选 .user.js

### 步骤 4：验证
- 打开小鹅通课程页 → Tampermonkey 图标出现**红色角标数字** = 脚本在运行
- 进回放页点播放几秒 → 点猫抓图标 → 资源列表出现 m3u8 = 链路通

## 三、Tabbit 备选（美团 AI 浏览器）

- **前提**：Tabbit 是 Chromium 内核，官网支持从 Chrome/Edge 迁移扩展
- 入口：`tabbit://extensions`（打不开则在设置找【扩展程序】）
- 加载方式与 Chrome 相同；若 Tabbit 未开放【开发者模式】→ 走兜底：Chrome 装好扩展后【从 Chrome 迁移扩展程序】

## 四、manifest 权限修复（MV3 兼容）

非商店 crx 解压版可能带 MV2 遗留权限，Chrome 会报错禁用。自动修复：

```bash
python scripts/fix_manifest.py --dir "download/extracted/tampermonkey"
```

修复内容：
- 删除 `"webRequestBlocking"`（MV2 专属，MV3 不允许）——报错 `'webRequestBlocking' requires manifest version of 2 or lower`
- 把 `"chrome://favicon/"` 替换为 `"favicon"`（MV3 合法写法）——报错 `Permission 'chrome://favicon/' is unknown`
- 修完重新加载扩展

**为什么不影响功能**：油猴脚本抓 m3u8 走 content script 挂钩（indexOf/JSON.parse/XHR），不依赖 webRequestBlocking。

## 五、油猴脚本机制（v0.10 已核实源码）

- 全站匹配 `@match https/*`
- 挂钩 `String.prototype.indexOf`（捕 #EXTM3U）、`JSON.parse`（递归找 video_urls）、`XMLHttpRequest.open`（XHR 响应找媒体）
- `video_urls` 以 `__ba` 结尾时 base64 解码（`@→1 #→2 $→3 %→4` 替换）得真实视频对象
- 重拼真实 ts 地址（host/path/param 缓存自 confusion_m3u8 结构）
- 真实密钥：优先 `window.__user_id`，否则 cookie `userInfo` 里的 user_id，拼 `&uid=` 请求密钥接口，与 user_id 字节异或还原 key
- 通过 `window.postMessage({action:"catCatchAddMedia"/"catCatchAddKey", ...})` 发给猫抓

## 六、反模式

| 反模式 | 后果 | 正确做法 |
|--------|------|---------|
| 拖 .user.js 进浏览器 | file:// 源被拦 | 本地 http 服务 |
| 选错目录（进入文件夹内部） | 报【清单文件缺失】 | 选目录本身 |
| 从 ffmpeg.bmmmd.com 等非官方源下工具 | 安全风险 | 只用官方源/已就位资产 |
| 装完不验证红色角标 | 以为装了其实没生效 | 必须看角标数字 |
