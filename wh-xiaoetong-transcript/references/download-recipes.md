# 下载核心方法论（RED 必读）

> 本文件是 wh-xiaoetong-transcript 的核心方法论。执行下载前必须读。
> 位置：`outputs/小鹅通转写工作流/downloader/N_m3u8DL-RE/N_m3u8DL-RE.exe`

---

## 一、m3u8 结构快速判定

小鹅通回放 m3u8 URL 特征：
```
https://encrypt-k-vod.xet.tech/{video_id}vodcq{cid}/{vid}vodcq{...}/playlist_eof.m3u8?sign=...&t=...&us=...&time=...&uuid=...
```

| 段 | 含义 | 用途 |
|----|------|------|
| `{video_id}vodcq`（URL 路径第二段） | 视频 ID | **防重复判定的核心依据** |
| `sign/t/us/time/uuid` 参数 | 签名 + 时间戳 + 会话 | 带签名，过期失效，需在有效期内下载 |
| `playlist_eof.m3u8` | 主播放列表 | VOD 点播（非直播流） |

**判定是否直播流**：URL 域名含 `liveplay-byte` / `liveplay.xiaoe-live.com` / `webrtc` = 直播流，**不是回放**，拒绝使用。回放必须是 `encrypt-k-vod.xet.tech` 点播域。

**判定是否加密**：下载前 curl m3u8 内容，含 `#EXT-X-KEY` = AES-128 加密（N_m3u8DL-RE 自动解密）；无 = 直接合并。

## 二、防重复下载判定（铁律）

m3u8 到手后，在下载前先判定：

```
Step 1: 提取 video ID（URL 路径 `/{id}vodcq/` 段）
Step 2: 与 downloads/ 已有 mp4 对比
  ├─ video ID 相同 → 同视频新签名 → 拒绝下载，说明"这是上一节的同视频"
  ├─ video ID 不同 → 检查 ffprobe 时长是否与已有不同
  │   ├─ 时长相同 → 抽音频指纹对比（同时间段 10s PCM md5）
  │   └─ 时长不同 → 真新视频，放行
  └─ 无历史记录 → 放行
```

**音频指纹对比命令**（存疑时用）：
```bash
ffmpeg -ss 600 -t 10 -i "旧.mp4" -f s16le -ac 1 -ar 16000 - 2>/dev/null | md5sum
ffmpeg -ss 600 -t 10 -i "新.mp4" -f s16le -ac 1 -ar 16000 - 2>/dev/null | md5sum
# 两组 md5 全一致 = 同一视频（容器封装差异不影响音频内容）
```

## 三、下载命令（已验证）

```bash
./downloader/N_m3u8DL-RE/N_m3u8DL-RE.exe "<m3u8完整URL>" \
  --save-dir "downloads/_tmp" \
  -H "Referer: https://YOUR_XIAOETONG_HOST/" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)" \
  --thread-count 16
```

参数说明：
- `--save-dir`：输出目录，用 `_tmp` 过渡，命名后再移动到正式名
- `-H Referer`：防盗链必需，用课程页域名（`YOUR_XIAOETONG_HOST`）
- `-H User-Agent`：伪装浏览器 UA
- `--thread-count 16`：并行拉流，实测 ~67MB/s
- 输出文件名：`playlist_eof_YYYY-MM-DD_HH-MM-SS.mp4`（需按命名铁律改名）

**验证产物**：
```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,codec_type,width,height -of default=noprint_wrappers=1 "<mp4>"
```
确认：时长与 m3u8 `#EXTINF` 总和一致、分辨率/编码正确、大小合理（1080p ≈ 1.5GB/90min）。

## 四、实测性能基线（本机 2026-09 验证）

| 节 | 时长 | 分片 | 大小 | 下载 | 转写(large-v3 GPU) |
|----|------|------|------|------|-------------------|
| 52 | 82 min | 999 | 1.48 GiB | ~67MB/s | 422 s |
| 51 | 102 min | 1238 | 1.51 GiB | - | 658 s |
| 53 | 90 min | 1094 | 1.46 GiB | - | 454 s |

- 下载速度约 67MB/s（本地网络）
- 转写约 7 分钟/90 分钟视频（GPU cuda/float16）
- 100 节批量预计 ≈ 12 小时 GPU 时间，模型权重已缓存

## 五、批量策略

- 逐节重复：用户在浏览器点播放 → 猫抓复制 m3u8 + 播放页标题 → 发 AI → pipeline
- **先手动跑通 1-2 节再谈批量**，不重蹈自研覆辙
- 自动化批量（Playwright 逐节开播放页触发猫抓）是未来项，当前未验证

## 六、反模式

| 反模式 | 后果 | 正确做法 |
|--------|------|---------|
| 不查 video ID 直接下载 | 同视频重复浪费 | 先判定再下载 |
| 用直播流地址（liveplay） | 下载的是实时流不是回放 | 必须是 encrypt-k-vod 点播域 |
| 不带 Referer | 防盗链 403 | 必须带课程页 Referer |
| 下载完不 ffprobe | 分片缺失/损坏未知 | 必须验证产物 |

## 七、实战记录

- **案例 1（52 节）**：首个 m3u8 直连可访问（HTTP 200，无 EXT-X-KEY），N_m3u8DL-RE 16 线程下载 999 分片全齐，ffprobe 验证 4948.8s/1080p。
- **案例 2（同视频新签名）**：第二个 m3u8 video ID `2f17defe...` 与 52 节完全相同、大小 1,593,474,428 字节一致 → 抽两处音频指纹 md5 全同 → 判定同视频，拒绝重复转写。
- **案例 3（53 节）**：video ID `46c4c861` 新视频，转码时间戳 2026-08-29 与标题日期吻合，1094 分片全齐。
