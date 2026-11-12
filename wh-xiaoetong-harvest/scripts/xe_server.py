#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xe_server.py — 小鹅通课程批量采集服务器（本地接收端）

职责：接收油猴脚本【小鹅通课程批量采集器】上报的结构化清单（m3u8 文本 + 解密密钥 +
真实标题），落盘到工作目录，供 xe_pipeline.py 下载与整理。只监听 127.0.0.1，
不对外网开放。

用法：
    python xe_server.py --port 8771 --workdir "./xiaoe-harvest"

端点：
    POST /ingest   接收 {kind: lesson|key|course|course_list, ...}
    GET  /status   汇总 {lessons, keyed, captured, courses, course_list, updated_at}
    GET  /items    完整 state.json 内容
    GET  /health   同 /status
"""
import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Store:
    """state.json 单一真源：lessons（按 video_id 合并）、courses、course_list。"""

    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.raw_dir = workdir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = workdir / "state.json"
        self.lock = threading.Lock()
        self.state = {"lessons": {}, "courses": {}, "course_list": [], "updated_at": ""}
        if self.state_path.exists():
            try:
                loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and "lessons" in loaded:
                    self.state = loaded
            except Exception as exc:
                print(f"[xe_server] state.json 读取失败，使用空白状态: {exc}", flush=True)

    def save_locked(self):
        self.state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        tmp = self.state_path.with_name("state.json.tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.state_path)

    def ingest(self, payload: dict) -> dict:
        kind = payload.get("kind", "")
        with self.lock:
            if kind == "lesson":
                return self._lesson_locked(payload)
            if kind == "key":
                return self._key_locked(payload)
            if kind == "course":
                return self._course_locked(payload)
            if kind == "course_list":
                return self._course_list_locked(payload)
            return {"ok": False, "error": f"未知 kind: {kind}"}

    def _lesson_locked(self, item: dict) -> dict:
        m3u8 = (item.get("m3u8") or "").strip()
        if not m3u8.startswith("#EXTM3U"):
            return {"ok": False, "error": "m3u8 缺少 #EXTM3U 头，拒绝入库"}
        # 脏数据清洗：旧版钩子会给绝对 ts 地址再拼一次 &param，导致 sign/t/us 参数
        # 每行出现 2 次（CDN 必 403）。清洗规则：保留第一段完整参数，截断第二个 &sign= 起
        # 的重复段。行内不含 http 的（相对路径）不处理。
        cleaned_lines = []
        for _line in m3u8.splitlines():
            if _line.startswith("http") and _line.count("sign=") > 1:
                pos = _line.find("sign=")
                pos2 = _line.find("sign=", pos + 5)
                if pos2 > 0:
                    _line = _line[:pos2 - 1]
            cleaned_lines.append(_line)
        m3u8 = "\n".join(cleaned_lines)
        vid = (item.get("video_id") or "").strip()
        if not vid:
            return {"ok": False, "error": "video_id 为空，拒绝入库"}
        has_key = "#EXT-X-KEY" in m3u8
        (self.raw_dir / f"{vid}.m3u8").write_text(m3u8 + "\n", encoding="utf-8")

        cur = self.state["lessons"].get(vid)
        if cur is None:
            cur = {
                "video_id": vid,
                "title": item.get("title") or vid,
                "chapter": item.get("chapter") or "",
                "course_id": item.get("course_id") or "",
                "course_title": item.get("course_title") or "",
                "page_url": item.get("page_url") or "",
                "m3u8_url": item.get("m3u8_url") or "",
                "has_key": has_key,
                "key_b64": item.get("key_b64") or "",
                "uid": item.get("uid") or "",
                "captured_at": item.get("captured_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "captured",
            }
        else:
            # 首个标题（目录页显示名）保持不变；两类情况替换 m3u8：
            #   1) 旧的无密钥、新的带密钥
            #   2) 新的显著更短（旧版钩子会把绝对 ts 地址再拼一次 &param，
            #      导致 sign/t/us 参数重复，文本明显变长；更短 = 更干净 = 优先）
            old_raw = ""
            old_file = self.raw_dir / f"{vid}.m3u8"
            if old_file.exists():
                try:
                    old_raw = old_file.read_text(encoding="utf-8")
                except Exception:
                    old_raw = ""
            cleaner = bool(old_raw) and (len(m3u8) < len(old_raw) * 0.93)
            if (has_key and not cur.get("has_key")) or cleaner:
                cur["m3u8_url"] = item.get("m3u8_url") or cur.get("m3u8_url", "")
                cur["has_key"] = has_key or cur.get("has_key", False)
                cur["captured_at"] = item.get("captured_at") or cur.get("captured_at", "")
            if item.get("chapter") and not cur.get("chapter"):
                cur["chapter"] = item["chapter"]
            if item.get("course_title") and not cur.get("course_title"):
                cur["course_title"] = item["course_title"]
        if item.get("key_b64") and not cur.get("key_b64"):
            cur["key_b64"] = item["key_b64"]
            cur["uid"] = item.get("uid") or cur.get("uid", "")
        if cur.get("key_b64"):
            (self.raw_dir / f"{vid}.key.b64").write_text(cur["key_b64"], encoding="utf-8")
        cur["status"] = "keyed" if (cur.get("key_b64") or not cur.get("has_key")) else "captured"
        self.state["lessons"][vid] = cur
        self.save_locked()
        total = len(self.state["lessons"])
        keyed = sum(1 for v in self.state["lessons"].values() if v.get("status") == "keyed")
        print(f"[ingest] lesson {vid} 《{cur['title']}》 key={'Y' if cur.get('key_b64') else 'N'} 进度 {keyed}/{total}", flush=True)
        return {"ok": True, "video_id": vid, "lessons": total, "keyed": keyed}

    def _key_locked(self, item: dict) -> dict:
        vid = (item.get("video_id") or "").strip()
        key_b64 = (item.get("key_b64") or "").strip()
        if not vid or not key_b64:
            return {"ok": False, "error": "key 上报缺少 video_id 或 key_b64"}
        cur = self.state["lessons"].get(vid)
        if cur is None:
            cur = {"video_id": vid, "title": vid, "status": "key-only",
                   "captured_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            self.state["lessons"][vid] = cur
        cur["key_b64"] = key_b64
        cur["uid"] = item.get("uid") or cur.get("uid", "")
        if cur.get("has_key"):
            cur["status"] = "keyed"
        (self.raw_dir / f"{vid}.key.b64").write_text(key_b64, encoding="utf-8")
        self.save_locked()
        print(f"[ingest] key {vid} 已合入", flush=True)
        return {"ok": True, "video_id": vid}

    def _course_locked(self, item: dict) -> dict:
        cid = (item.get("course_id") or "").strip()
        if not cid:
            return {"ok": False, "error": "course_id 为空"}
        cur = self.state["courses"].get(cid) or {}
        cur.update({
            "course_id": cid,
            "course_title": item.get("course_title") or cur.get("course_title") or "",
            "page_url": item.get("page_url") or cur.get("page_url") or "",
            "seen_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.state["courses"][cid] = cur
        self.save_locked()
        print(f"[ingest] course {cid} 《{cur['course_title']}》", flush=True)
        return {"ok": True}

    def _course_list_locked(self, item: dict) -> dict:
        cid = (item.get("course_id") or "").strip()
        if not cid:
            return {"ok": False, "error": "course_id 为空"}
        entry = {"course_id": cid, "title": item.get("title") or "", "url": item.get("url") or ""}
        self.state["course_list"] = [x for x in self.state["course_list"] if x.get("course_id") != cid]
        self.state["course_list"].append(entry)
        self.save_locked()
        print(f"[ingest] course_list {cid} 《{entry['title']}》 共 {len(self.state['course_list'])} 门", flush=True)
        return {"ok": True}


class Handler(BaseHTTPRequestHandler):
    store = None  # type: Store

    def _send(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/status", "/health"):
            with self.store.lock:
                lessons = self.store.state["lessons"]
                summary = {
                    "ok": True,
                    "lessons": len(lessons),
                    "keyed": sum(1 for v in lessons.values() if v.get("status") == "keyed"),
                    "captured": sum(1 for v in lessons.values() if v.get("status") == "captured"),
                    "courses": len(self.store.state["courses"]),
                    "course_list": len(self.store.state["course_list"]),
                    "updated_at": self.store.state.get("updated_at", ""),
                    "workdir": str(self.store.workdir),
                }
            self._send(200, summary)
        elif path == "/items":
            with self.store.lock:
                self._send(200, self.store.state)
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        if path != "/ingest":
            self._send(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            self._send(400, {"ok": False, "error": f"JSON 解析失败: {exc}"})
            return
        result = self.store.ingest(payload)
        self._send(200 if result.get("ok") else 422, result)

    def log_message(self, fmt, *args):
        pass  # 静默默认访问日志，保留自定义 ingest 日志


def main():
    ap = argparse.ArgumentParser(description="小鹅通课程批量采集服务器")
    ap.add_argument("--port", type=int, default=8771)
    ap.add_argument("--workdir", default=str(Path.cwd() / "xe-harvest-work"),
                    help="工作目录（state.json + raw/ 落盘处）")
    args = ap.parse_args()
    workdir = Path(args.workdir).resolve()
    store = Store(workdir)
    Handler.store = store
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"[xe_server] 采集服务器已启动 http://127.0.0.1:{args.port}", flush=True)
    print(f"[xe_server] 工作目录 {workdir}", flush=True)
    print(f"[xe_server] 油猴脚本配置 server=http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[xe_server] 已停止", flush=True)


if __name__ == "__main__":
    main()
