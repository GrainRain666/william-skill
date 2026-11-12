# xe-data-chain — m3u8 采集与解密链路（必读）

> 本文件是 wh-xiaoetong-harvest 的核心方法论。执行采集与下载前必须读。
> 来源：Greasy Fork 461963“小鹅通 通用m3u8获取”v0.10 源码复核 + cat-catch 2.7.2 源码查证 + 2026-09-03 实测清单。

---

## 一、两种已验证的回放 m3u8 形态

### 形态 A：v-vod-k DRM 形态（本课程实测，AES-128 加密）

```
https://v-vod-k.xiaoeknow.com/{账户}/APP_YOUR_ID/video/b_u_{id}/{vid}/drm/main.m3u8?sign=...&t=...&us=...
https://v-vod-k.h5.xed.plus/...（镜像域）
```

- 媒体播放列表直接含 ts 分片与 `#EXT-X-KEY:METHOD=AES-128,URI="..."` 
- ts 相对路径需按页面下发的 `ext {host, path, param}` 重拼：`{host}/{path}/{分片}&{param}`
- 密钥接口返回值 = 真实 AES key 与 user_id 的 UTF-8 字节序列**逐字节异或**后的结果

### 形态 B：encrypt-k-vod vodcq 形态（社区包 52/51/53 节验证）

```
https://encrypt-k-vod.xet.tech/{account}vodcq{cid}/{video_id}vodcq{...}/playlist_eof.m3u8?sign=&t=&us=&time=&uuid=
```

- URL 路径第二段 `/{id}vodcq/` 的 `{id}`（倒数第二段）即视频 ID，防重复判定的核心依据
- 可能无 `#EXT-X-KEY`（明文），N_m3u8DL-RE / ffmpeg 直接下载

**直播流判定**：域名含 `liveplay-byte` / `liveplay.xiaoe-live.com` / `webrtc` = 直播流不是回放，拒绝。

## 二、video_urls 解码链（油猴脚本核心逻辑）

1. hook `JSON.parse` / `XMLHttpRequest.open` / `String.prototype.indexOf(#EXTM3U)`
2. JSON 树中找到 `video_urls` 字段，值为 base64 且以 `__ba` 结尾
3. 去 `__ba` 尾标，`@ # $ %` 分别替换为 `1 2 3 4`，`atob` 得 JSON 数组
4. 数组每项 `{url, ext:{host, path, param}}`：`url` 为 m3u8 地址（含签名），`ext` 用于重拼 ts 相对路径
5. 多清晰度/镜像项：脚本按序尝试，首个 fetch 成功且含 `#EXTM3U` 的即上报

## 三、密钥获取（2026-09-03 实测修正：直取不加 uid，勿 XOR）

```
密钥 URL = m3u8 内 #EXT-X-KEY 的 URI（原文不动，不追加 &uid）
密钥字节 = 直接 GET 该 URL 的响应体（16 字节，本课程为 ASCII 十六进制串如 317af99ca1cc7ccf，直接作 AES key）
IV      = m3u8 #EXT-X-KEY 行 IV=0x... 的值（左补零到 16 字节），无则用分片序号
```

- 实测：v-vod-k drm/main.m3u8 用【直取密钥 + IV=0x00000000】AES-128-CBC 解密分片，
  TS 0x47 同步 414/414、时长与 video_length 完全吻合（猫抓 m3u8.js 正是 fetch(decryptdata.uri) 直取，无 uid/XOR）。
- **反例教训**：mz 油猴脚本的"加 &uid 再与 user_id 字节 XOR"适用于部分部署；对本课程反而得到错误 key（解密全乱）。
  先试直取；仅当直取结果非 16 字节或解密失败时再考虑 XOR 变体。

## 四、本地采集服务器协议（xe_server.py）

```
POST /ingest   Content-Type: application/json
  kind=lesson  {video_id, title, chapter, course_id, course_title, page_url,
                m3u8(重拼后的完整文本), m3u8_url(源地址), has_key,
                key_b64(已还原密钥), uid, captured_at}
  kind=key     {video_id, key_b64, uid}                       # 密钥晚于媒体到达时补报
  kind=course  {course_id, course_title, page_url}            # 课程页标题
  kind=course_list {course_id, title, url}                    # learnIndex 已购清单
GET  /status   {lessons, keyed, captured, courses, course_list, updated_at, workdir}
GET  /items    state.json 全量
```

- state.json 合并规则：同 video_id 首个标题（目录显示名）保持不变；新 m3u8 带密钥而旧的不带时替换 m3u8
- 落盘：`{workdir}/state.json` + `{workdir}/raw/{video_id}.m3u8` + `{video_id}.key.b64`
- 油猴侧 POST 失败自动进 localStorage 队列（12 秒重发）；油猴配置热更：
  `localStorage.setItem('xeHarvestCfg', JSON.stringify({server:"http://127.0.0.1:8771", enabled:true, auto:true}))`

## 五、m3u8 本地改写与喂流（xe_pipeline download 阶段）

```
逐行处理：
  #EXT-X-KEY 且 URI=""        → 丢弃该行（原脚本同样丢弃）
  #EXT-X-KEY 且 URI="http..." → 改写为 URI="key.bin"（相对路径，与 playlist 同目录）
  其余原样保留（ts 已是绝对地址）
配套：key.bin = base64decode(key_b64)；缺失 key 时报 key_missing 回采集阶段补
```

**喂流架构（2026-09-03 实测修正）**：ffmpeg 的 `-headers` / `-user_agent` 是 http/https
协议专属选项，对本地 file 输入会直接报 `Option not found`。因此 download 阶段会在
`workdir/dl` 上起一个 127.0.0.1 随机端口静态服务，ffmpeg 输入改为
`http://127.0.0.1:{port}/{video_id}/playlist.m3u8`——本地 key 与远端 ts 分段的请求
都带上 Referer/UA（Referer 默认取课时 page_url 源站，可用 `--referer` 覆盖）。

```bash
ffmpeg -y -hide_banner -allowed_extensions ALL \
  -protocol_whitelist file,http,https,tcp,tls,crypto \
  -headers "Referer: {课程页源站}/
User-Agent: Mozilla/5.0 ..." \
  -user_agent "Mozilla/5.0 ..." \
  -i "http://127.0.0.1:{port}/{video_id}/playlist.m3u8" \
  -map 0 -c copy -bsf:a aac_adtstoasc "{video_id}.mp4"
```

- 下载产物以 video_id 命名；最终标题在 organize 阶段决定（命名与下载解耦）
- 产物必须 ffprobe 校验时长（对比 #EXTINF 总和）与大小
- 局限：`#EXT-X-MAP`（fMP4 初始化段）本版本不做本地化；遇到分段 403/签名过期按
  `{video_id}/tool.log` 末尾排查，必要时回采集阶段重采该节

## 六、防重复判定（铁律）

```
Step 1: 提取 CDN video ID（形态 A 取路径倒数第二段；形态 B 取 /{id}vodcq/ 段）
Step 2: 与 workdir/history.json 对比
  ├─ video_id（页面层）命中 → 已下载过该课时，跳过
  ├─ cdn_id命中 → 同视频新签名，拒绝下载并说明
  └─ 无记录 →放行；下载成功后双键登记 {video_id, cdn_id, size, at}
```

存疑时音频指纹：`ffmpeg -ss 600 -t 10 -i 旧.mp4 -f s16le -ac 1 -ar 16000 - | md5sum`（两组一致 = 同视频）。

## 七、签名时效与目录页采集边界

- sign/t/us 有时效（实测数小时级）：**采集后 2 小时内下载**，跨天批量按"采集一批 → 立即下载一批"执行
- 目录页数据来自 JSON.parse hook：目录需滚动加载完全部章节再等 4 秒去抖启动；合集课程（需 sub_course_id）不在本版本范围
- 猫抓兼容桥保留：批量 iframe 内仍向顶层 postMessage，顶层改标题后发 catCatchAddMedia——仅供手动救急，文件名不保证（见 negative-results.md 负结果 3）
