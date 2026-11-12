// ==UserScript==
// @name         小鹅通课程批量采集器
// @namespace    https://94cat.com/
// @version      1.02
// @description  课程目录页自动收集章节视频，后台串行打开播放页抓取 m3u8+解密密钥，结构化清单 POST 到本地采集服务器（默认 http://127.0.0.1:8771）；同时保留猫抓桥接；单视频页原逻辑兼容
// @author       mz (modified for wh-xiaoetong-harvest)
// @match        https://*/*
// @match        http://*/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-start
// @license      GPL v3
// ==/UserScript==

(function () {
    'use strict';

    // ===================== 运行环境与域 guard =====================
    // Tampermonkey 有 @grant 时脚本运行在沙盒，页面对象必须经 unsafeWindow 访问
    const W = (typeof unsafeWindow !== "undefined") ? unsafeWindow : window;
    const TAG = "[XeHarvest]";

    const XE_HOST_RE = /xiaoe-tech\.com|xet\.pomoho\.com|xet\.tech|xiaoeknow\.com|xiaoe\.cn/i;
    const FORCE_FLAG = (typeof W.__XE_HARVEST_FORCE !== "undefined") && !!W.__XE_HARVEST_FORCE;
    if (!XE_HOST_RE.test(W.location.hostname) && !FORCE_FLAG) {
        return; // 非小鹅通域直接退出，不污染普通网页
    }

    const IS_TOP = (W.top === W.self);
    const URLext = new Map();               // host -> {host, path, param}（indexOf 钩子路径的拼接信息）

    // ===================== 配置（localStorage 可热更） =====================
    const CFG_KEY = "xeHarvestCfg";
    function readCfg() {
        const def = { server: "http://127.0.0.1:8771", enabled: true, auto: true };
        try {
            const raw = W.localStorage.getItem(CFG_KEY);
            if (raw) { Object.assign(def, JSON.parse(raw) || {}); }
        } catch (e) { }
        return def;
    }

    // ===================== 本地服务器上报（GM_xmlhttpRequest 跨 mixed-content） =====================
    const QUEUE_KEY = "xeHarvestQueue";
    function queuePush(payload) {
        try {
            const arr = JSON.parse(W.localStorage.getItem(QUEUE_KEY) || "[]");
            arr.push(payload);
            W.localStorage.setItem(QUEUE_KEY, JSON.stringify(arr));
        } catch (e) { }
    }

    function postToServer(payload) {
        const cfg = readCfg();
        if (!cfg.enabled || !cfg.server) { queuePush(payload); return; }
        const body = JSON.stringify(payload);
        try {
            GM_xmlhttpRequest({
                method: "POST",
                url: cfg.server.replace(/\/$/, "") + "/ingest",
                data: body,
                headers: { "Content-Type": "application/json" },
                timeout: 10000,
                onerror: function () { queuePush(payload); },
                ontimeout: function () { queuePush(payload); }
            });
        } catch (e) {
            queuePush(payload);
        }
    }

    // 仅顶层页面启动队列重发循环（iframe 共享同源 localStorage，避免多实例重复发送）
    if (IS_TOP) {
        setInterval(function () {
            let arr = [];
            try { arr = JSON.parse(W.localStorage.getItem(QUEUE_KEY) || "[]"); } catch (e) { }
            if (!arr.length) return;
            const cfg = readCfg();
            if (!cfg.enabled || !cfg.server) return;
            const remain = [];
            let resent = 0;
            for (const p of arr) {
                if (resent < 20) {
                    resent++;
                    try {
                        GM_xmlhttpRequest({
                            method: "POST",
                            url: cfg.server.replace(/\/$/, "") + "/ingest",
                            data: JSON.stringify(p),
                            headers: { "Content-Type": "application/json" },
                            timeout: 8000,
                            onerror: function () { remain.push(p); },
                            ontimeout: function () { remain.push(p); }
                        });
                    } catch (e) { remain.push(p); }
                } else {
                    remain.push(p);
                }
            }
            try { W.localStorage.setItem(QUEUE_KEY, JSON.stringify(remain)); } catch (e) { }
        }, 12000);
    }

    // ===================== 身份解析（批量 iframe / 单视频页） =====================
    function hashParam(key) {
        try {
            const m = W.location.hash.match(new RegExp("[#&]" + key + "=([^&]+)"));
            return m ? decodeURIComponent(m[1]) : "";
        } catch (e) { return ""; }
    }
    const IFRAME_NAME = IS_TOP ? "" : hashParam("catch-name");
    const IFRAME_ID = IS_TOP ? "" : hashParam("catch-id");
    const IFRAME_CHAPTER = IS_TOP ? "" : hashParam("catch-chapter");
    const IFRAME_COURSE = IS_TOP ? "" : hashParam("catch-course");
    const IFRAME_COURSE_NAME = IS_TOP ? "" : hashParam("catch-course-name");
    const BATCH_CHILD = (!IS_TOP && !!IFRAME_ID);

    function resolveVideoId() {
        if (IFRAME_ID) return IFRAME_ID;
        const m = W.location.pathname.match(/\/video\/(v_[0-9A-Za-z]{10,})/);
        if (m) return m[1];
        let h = 0;
        const s = W.location.href;
        for (let i = 0; i < s.length; i++) { h = ((h << 5) - h + s.charCodeAt(i)) | 0; }
        return "page-" + Math.abs(h);
    }

    // ===================== 状态 =====================
    const collectedItems = new Map();       // videoId -> {id, title, chapter}
    const keyStore = new Map();             // videoId -> {key_b64, uid}
    const postedSign = new Set();           // videoId + "|" + m3u8.length + "|" + head200 去重
    let courseTitleCandidate = "";
    let batchStarted = false;
    let batchTimer = null;
    let originalTitle = null;

    function cleanTitle(t) {
        if (!t) return "";
        return String(t).replace(/\s+/g, " ").trim();
    }

    function pageUrlClean() {
        try {
            const u = new URL(W.location.href);
            u.hash = "";
            return u.toString();
        } catch (e) { return W.location.href; }
    }

    // ===================== 成果上报：m3u8 文本 =====================
    function sendMediaText(m3u8Text, srcUrl) {
        const vid = resolveVideoId();
        const sign = vid + "|" + m3u8Text.length + "|" + String(m3u8Text).slice(0, 200);
        if (postedSign.has(sign)) return;
        postedSign.add(sign);
        if (!/#EXTM3U/.test(m3u8Text)) return;

        const ks = keyStore.get(vid);
        postToServer({
            kind: "lesson",
            video_id: vid,
            title: cleanTitle(IFRAME_NAME) || cleanTitle(W.document.title || ""),
            chapter: cleanTitle(IFRAME_CHAPTER),
            course_id: IFRAME_COURSE || (W.location.pathname.match(/(course_[0-9A-Za-z]+)/) || ["", ""])[1] || "",
            course_title: cleanTitle(IFRAME_COURSE_NAME) || cleanTitle(courseTitleCandidate),
            page_url: pageUrlClean(),
            m3u8: m3u8Text,
            m3u8_url: srcUrl || "",
            has_key: /#EXT-X-KEY/.test(m3u8Text),
            key_b64: ks ? ks.key_b64 : "",
            uid: ks ? ks.uid : "",
            captured_at: new Date().toISOString()
        });

        if (BATCH_CHILD) {
            // 猫抓兼容桥：交回顶层走改标题后转发（顶层逻辑见下）
            try {
                W.top.postMessage({
                    action: "__xe_batch_media",
                    id: IFRAME_ID,
                    name: IFRAME_NAME,
                    m3u8: m3u8Text
                }, "*");
            } catch (e) { }
        } else {
            sendDirectToCatCatch(m3u8Text);
        }
    }

    function sendDirectToCatCatch(m3u8Text) {
        try {
            const blob = new W.Blob([new TextEncoder("utf-8").encode(m3u8Text)]);
            const url = W.URL.createObjectURL(blob);
            W.postMessage({ action: "catCatchAddMedia", url: url, href: W.location.href, ext: "m3u8" });
        } catch (e) { }
    }

    // ===================== 成果上报：解密密钥 =====================
    function sendKeyUpdate(videoId, keyArray, uid) {
        let bin = "";
        try {
            const u8 = new Uint8Array(keyArray);
            let s = "";
            for (let i = 0; i < u8.length; i++) { s += String.fromCharCode(u8[i]); }
            bin = W.btoa(s);
        } catch (e) { return; }
        keyStore.set(videoId, { key_b64: bin, uid: uid || "" });
        postToServer({
            kind: "key",
            video_id: videoId,
            key_b64: bin,
            uid: uid || "",
            page_url: pageUrlClean(),
            captured_at: new Date().toISOString()
        });
        if (BATCH_CHILD) {
            try {
                W.top.postMessage({ action: "__xe_batch_key", id: IFRAME_ID, key: keyArray }, "*");
            } catch (e) { }
        } else {
            try {
                W.postMessage({ action: "catCatchAddKey", key: keyArray, href: W.location.href });
            } catch (e) { }
        }
    }

    // ===================== 顶层：猫抓兼容桥（改标题后转发） =====================
    if (IS_TOP) {
        W.addEventListener("message", function (event) {
            const d = event.data;
            if (!d || typeof d !== "object") return;
            if (d.action === "__xe_batch_media" && d.m3u8) {
                try {
                    if (originalTitle === null) originalTitle = W.document.title;
                    if (d.name) W.document.title = d.name;
                } catch (e) { }
                sendDirectToCatCatch(d.m3u8);
            } else if (d.action === "__xe_batch_key" && d.key) {
                try {
                    W.postMessage({ action: "catCatchAddKey", key: d.key, href: W.location.href });
                } catch (e) { }
            }
        }, false);
    }

    // ===================== 课程清单收集（学习主页 learnIndex 等） =====================
    const postedCourses = new Set();
    const ID_KEY_RE = /^(course_id|product_id|resource_id|spc_id|goods_id|id)$/i;
    const ID_VAL_RE = /^(course_|spc_|v_|l_|p_)[0-9A-Za-z]{10,}$/;
    const TITLE_KEY_RE = /^(title|name|content_name|video_title|goods_name|resource_title|chapter_title|article_title|column_title)$/;

    function collectCourseList(data) {
        let found = 0;
        walk(data, null, 0);
        function walk(node, ctx, depth) {
            if (depth > 25 || found > 200) return;
            if (Array.isArray(node)) {
                for (const n of node) walk(n, ctx, depth + 1);
                return;
            }
            if (!node || typeof node !== "object") return;
            let id = null, title = null, url = null;
            for (const k in node) {
                const v = node[k];
                if (typeof v === "string") {
                    if (id === null && ID_KEY_RE.test(k) && ID_VAL_RE.test(v) && !/^v_/.test(v)) id = v;
                    if (title === null && TITLE_KEY_RE.test(k) && v && !ID_VAL_RE.test(v)) title = cleanTitle(v);
                    if (url === null && /^(url|jump_url|link|href|page_url|play_url)$/.test(k)
                        && /\/p\/(course|content|tpl)\//.test(v)) url = v;
                }
            }
            if (id && title && !postedCourses.has(id)) {
                postedCourses.add(id);
                found++;
                postToServer({
                    kind: "course_list",
                    course_id: id,
                    title: title,
                    url: url || "",
                    page_url: pageUrlClean(),
                    captured_at: new Date().toISOString()
                });
            }
            for (const k in node) {
                const v = node[k];
                if (v && typeof v === "object") walk(v, null, depth + 1);
            }
        }
    }

    // ===================== 课程页章节与课时收集（含章节上下文） =====================
    function decodeHtmlEntities(str) {
        if (!str || String(str).indexOf("&") === -1) return str;
        try {
            const el = W.document.createElement("textarea");
            el.innerHTML = str;
            return el.value;
        } catch (e) { return str; }
    }

    function addLesson(id, title, chapter) {
        if (!id || !title) return;
        if (collectedItems.has(id)) return;
        collectedItems.set(id, { id: id, title: title, chapter: chapter || "" });
        maybeStartBatch();
    }

    function collectCourseItems(data) {
        walk(data, { chapter: "", parentTitle: "" }, 0);
        function isTitleKey(k) { return TITLE_KEY_RE.test(k); }
        function walk(node, ctx, depth) {
            if (depth > 25) return;
            if (Array.isArray(node)) {
                for (const n of node) walk(n, ctx, depth + 1);
                return;
            }
            if (!node || typeof node !== "object") return;
            let localTitle = null;
            let hasArray = false;
            for (const k in node) {
                const v = node[k];
                if (typeof v === "string") {
                    if (localTitle === null && isTitleKey(k) && v && !ID_VAL_RE.test(v)) {
                        localTitle = cleanTitle(decodeHtmlEntities(v));
                    }
                    if (courseTitleCandidate === "" && ID_KEY_RE.test(k) && /^course_/.test(v)
                        && localTitle && !("resource_id" in node)) {
                        courseTitleCandidate = localTitle;
                    }
                } else if (Array.isArray(v) && v.length > 0) {
                    hasArray = true;
                }
            }
            // 同时具备标题与子数组的对象视为章节容器，其标题向下传递为章节上下文
            const nextCtx = (localTitle && hasArray)
                ? { chapter: localTitle, parentTitle: localTitle }
                : { chapter: ctx.chapter, parentTitle: localTitle || ctx.parentTitle };
            for (const k in node) {
                const v = node[k];
                if (typeof v === "string") {
                    if (!isTitleKey(k) && ID_KEY_RE.test(k) === false && /^v_[0-9A-Za-z]{10,}$/.test(v)) {
                        addLesson(v, localTitle || ctx.parentTitle, nextCtx.chapter);
                    } else if (ID_KEY_RE.test(k) && /^v_[0-9A-Za-z]{10,}$/.test(v)) {
                        addLesson(v, localTitle || ctx.parentTitle, nextCtx.chapter);
                    }
                } else if (v && typeof v === "object") {
                    walk(v, nextCtx, depth + 1);
                }
            }
        }
        maybePostCourse();
    }

    function fallbackCourseTitle() {
        try {
            const t = (W.document.title || "").trim();
            return t.replace(/[-_|]\s*(小鹅通|学员版|线上学习).*$/i, "").trim();
        } catch (e) { return ""; }
    }

    function maybePostCourse() {
        if (IS_TOP && courseTitleCandidate === "") courseTitleCandidate = fallbackCourseTitle();
        if (!IS_TOP || courseTitleCandidate === "") return;
        const m = W.location.pathname.match(/(course_[0-9A-Za-z]+)/);
        const cid = m ? m[1] : "";
        if (!cid || postedCourses.has("course-page:" + cid)) return;
        postedCourses.add("course-page:" + cid);
        postToServer({
            kind: "course",
            course_id: cid,
            course_title: courseTitleCandidate,
            page_url: pageUrlClean(),
            captured_at: new Date().toISOString()
        });
    }

    function isCourseListPage() {
        return /\/p\/course\/(ecourse|video|spc|content)\//.test(W.location.pathname)
            || /learnIndex/.test(W.location.href);
    }

    // ===================== 批量队列：串行后台 iframe =====================
    function maybeStartBatch() {
        if (!readCfg().auto || batchStarted || collectedItems.size === 0) return;
        if (batchTimer) clearTimeout(batchTimer);
        batchTimer = setTimeout(startBatch, 4000);   // 去抖：等目录数据到齐再启动
    }

    function buildVideoUrl(item) {
        let courseId = "";
        const m = W.location.pathname.match(/(course_[0-9A-Za-z]+)/);
        if (m) courseId = m[1];
        let productId = courseId;
        try {
            const q = new URLSearchParams(W.location.search);
            productId = q.get("product_id") || courseId;
        } catch (e) { }
        return W.location.origin + "/p/course/video/" + item.id
            + "?product_id=" + encodeURIComponent(productId)
            + "&course_id=" + encodeURIComponent(courseId)
            + "&sub_course_id=";
    }

    function startBatch() {
        if (batchStarted) return;
        batchStarted = true;
        const items = [...collectedItems.values()];
        const queue = items.slice();
        let doneCount = 0;
        toast(`小鹅通批量采集：发现 ${items.length} 个视频，开始后台逐个获取，请保持本页面打开`);
        console.log(`${TAG} 共收集到 ${items.length} 个视频`);

        function next() {
            if (!queue.length) {
                toast(`小鹅通批量采集：完成，共 ${doneCount} 个视频已上报本地服务器（缺失项见 console）`);
                console.log(`${TAG} 队列处理完毕，共 ${doneCount} 个成功`);
                try {
                    if (originalTitle !== null) W.document.title = originalTitle;
                } catch (e) { }
                return;
            }
            const item = queue.shift();
            const pageUrl = buildVideoUrl(item);
            console.log(`${TAG} (${doneCount + 1}/${items.length}) 加载: ${item.title} -> ${pageUrl}`);

            const iframe = W.document.createElement("iframe");
            iframe.style.cssText = "position:fixed;left:-2000px;top:0;width:900px;height:600px;border:0;opacity:0;pointer-events:none;";
            iframe.setAttribute("aria-hidden", "true");
            iframe.src = pageUrl
                + (pageUrl.indexOf("#") === -1 ? "#" : "&")
                + "catch-name=" + encodeURIComponent(item.title)
                + "&catch-id=" + encodeURIComponent(item.id)
                + "&catch-chapter=" + encodeURIComponent(item.chapter || "")
                + "&catch-course=" + encodeURIComponent(IFRAME_COURSE || (W.location.pathname.match(/(course_[0-9A-Za-z]+)/) || ["", ""])[1] || "")
                + "&catch-course-name=" + encodeURIComponent(IFRAME_COURSE_NAME || courseTitleCandidate || "");

            let finished = false;
            let msgHandler = null;
            function finish(extraWait) {
                if (finished) return;
                finished = true;
                if (msgHandler) W.removeEventListener("message", msgHandler);
                setTimeout(function () {
                    try { iframe.remove(); } catch (e) { }
                    setTimeout(next, 800);
                }, extraWait || 0);
            }

            msgHandler = function (e) {
                const d = e.data;
                if (!d || typeof d !== "object" || d.id !== item.id) return;
                if (d.action === "__xe_batch_media") {
                    doneCount++;
                    console.log(`${TAG} 已获取: ${item.title}`);
                    finish(3000);
                }
            };
            W.addEventListener("message", msgHandler);

            setTimeout(function () { finish(0); }, 35000);  // 兜底超时跳过

            iframe.addEventListener("load", function () {
                setTimeout(function () {
                    try {
                        const idoc = iframe.contentDocument;
                        if (idoc) {
                            const v = idoc.querySelector("video");
                            if (v) { try { v.muted = true; } catch (e) { } }
                            const btn = idoc.querySelector(".xgplayer-start,.xgplayer-play");
                            if (btn) btn.click();
                        }
                    } catch (e) { }
                }, 2500);
            });

            (W.document.body || W.document.documentElement).appendChild(iframe);
        }

        setTimeout(next, 1200);
    }

    // ===================== 页面提示 =====================
    let toastTimer = null;
    function toast(text) {
        if (!IS_TOP) return;
        try {
            let box = W.document.getElementById("xe-harvest-toast");
            if (!box) {
                box = W.document.createElement("div");
                box.id = "xe-harvest-toast";
                box.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;"
                    + "background:#f2f2f2;color:#1a1a1a;border:1px solid #ccc;border-radius:6px;"
                    + "padding:10px 14px;font-size:13px;line-height:1.6;max-width:360px;"
                    + "box-shadow:0 2px 10px rgba(0,0,0,0.15);font-family:system-ui,sans-serif;";
                (W.document.body || W.document.documentElement).appendChild(box);
            }
            box.textContent = text;
            box.style.display = "block";
            if (toastTimer) clearTimeout(toastTimer);
            toastTimer = setTimeout(function () { box.style.display = "none"; }, 8000);
        } catch (e) { }
    }

    // ===================== String.prototype.indexOf 钩子（原版逻辑，沙盒安全化） =====================
    const _indexOf = W.String.prototype.indexOf;
    W.String.prototype.indexOf = function () {
        if (arguments[0] == "#EXTM3U") {
            try {
                parseSendM3U8(this);
                URLext.forEach(function (item) {
                    parseSendM3U8(this, item);
                }, this);
            } catch (e) { }
        }
        return _indexOf.apply(this, arguments);
    };
    try { W.String.prototype.indexOf.toString = function () { return _indexOf.toString(); }; } catch (e) { }

    // ===================== JSON.parse 钩子 =====================
    const _JSONparse = W.JSON.parse;
    W.JSON.parse = function () {
        let data = _JSONparse.apply(W.JSON, arguments);
        try { findMedia(data); } catch (e) { }
        try {
            if (IS_TOP && isCourseListPage()) {
                if (/learnIndex/.test(W.location.href)) collectCourseList(data);
                else collectCourseItems(data);
            }
        } catch (e) { }
        return data;
    };
    try { W.JSON.parse.toString = function () { return _JSONparse.toString(); }; } catch (e) { }

    // ===================== 媒体发现（video_urls 分支） =====================
    async function findMedia(data, raw = undefined, depth = 0) {
        for (let key in data) {
            if (typeof data[key] == "object") {
                if (depth > 25) { continue; }
                if (!raw) { raw = data; }
                findMedia(data[key], raw, ++depth);
                continue;
            }
            if (typeof data[key] == "string" && key == "video_urls" && data[key].slice(-4) == "__ba") {
                let base64 = data[key].replace("__ba", "");
                base64 = base64.replaceAll("@", "1").replaceAll("#", "2").replaceAll("$", "3").replaceAll("%", "4");
                let json;
                try { json = _JSONparse(atob(base64)); } catch (e) { continue; }
                if (!json || !json.length) { return; }
                // 顺序尝试：首个拉取成功且含 #EXTM3U 的清晰度即上报（避免批量模式下重复拉多路）
                const tryFetch = async (idx) => {
                    if (idx >= json.length) return;
                    const obj = json[idx];
                    try {
                        const resp = await W.fetch(obj.url);
                        const m3u8 = await resp.text();
                        if (!/#EXTM3U/.test(m3u8)) { await tryFetch(idx + 1); return; }
                        const lines = m3u8.split('\n');
                        let keyFlag = false;
                        for (let i = 0; i < lines.length; i++) {
                            if (lines[i] == '#EXT-X-ENDLIST') { break; }
                            if (!keyFlag && lines[i].includes("#EXT-X-KEY:METHOD=AES-128,URI=")) {
                                const match = lines[i].match(/URI="([^"]*)"/);
                                if (match && match[1]) {
                                    keyFlag = true;
                                    if (W.__user_id) {
                                        getKey(match[1] + "&uid=" + W.__user_id, W.__user_id);
                                    } else if (W.document.cookie) {
                                        for (let cookie of W.document.cookie.split(';')) {
                                            cookie = cookie.trim();
                                            if (cookie.substring(0, 10) == "userInfo={") {
                                                cookie = cookie.slice(9);
                                                cookie = isJSON(cookie);
                                                cookie && cookie.user_id && getKey(match[1] + "&uid=" + cookie.user_id, cookie.user_id);
                                                break;
                                            }
                                        }
                                    }
                                }
                                continue;
                            }
                            if (lines[i][0] != "#") {
                                if (lines[i].indexOf("http") !== 0 && obj.ext) {
                                    lines[i] = `${obj.ext.host}/${obj.ext.path}/${lines[i]}&${obj.ext.param}`;
                                }
                            }
                        }
                        sendMediaText(lines.join('\n'), obj.url);
                    } catch (e) {
                        await tryFetch(idx + 1);
                    }
                };
                tryFetch(0);
            } else if (data.confusion_m3u8 && data.ext) {
                URLext.set(data.ext.host, data.ext);
            } else if (data.app_id && data.host && data.param && data.path) {
                URLext.set(data.host, data);
            }
        }
    }

    // ===================== 密钥解密（uid 字节异或还原） =====================
    function uid2byte(uid) {
        const byteArray = new Array;
        for (let i = 0; i < uid.length; i++) {
            let temp = uid.charCodeAt(i);
            if (temp >= 65536 && temp <= 1114111) {
                byteArray.push(temp >> 18 & 7 | 240);
                byteArray.push(temp >> 12 & 63 | 128);
                byteArray.push(temp >> 6 & 63 | 128);
                byteArray.push(63 & temp | 128);
            } else if (temp >= 2048 && temp <= 65535) {
                byteArray.push(temp >> 12 & 15 | 224);
                byteArray.push(temp >> 6 & 63 | 128);
                byteArray.push(63 & temp | 128);
            } else if (temp >= 128 && temp <= 2047) {
                byteArray.push(temp >> 6 & 31 | 192);
                byteArray.push(63 & temp | 128);
            } else {
                byteArray.push(255 & temp);
            }
        }
        return byteArray;
    }

    function getKey(url, userId) {
        W.fetch(url).then(response => response.arrayBuffer())
            .then(buffer => {
                let newKey = [];
                buffer = new Uint8Array(buffer);
                const uidByte = uid2byte(userId);
                for (let i in buffer) {
                    newKey.push(buffer[i] ^ uidByte[i]);
                }
                sendKeyUpdate(resolveVideoId(), newKey, userId);
            }).catch(e => { });
    }

    // ===================== XHR 钩子（原版逻辑） =====================
    const _xhrOpen = W.XMLHttpRequest.prototype.open;
    W.XMLHttpRequest.prototype.open = function () {
        this.addEventListener("readystatechange", function (event) {
            try {
                const response = this.currentTarget ? this.currentTarget.response : this.response;
                const isJson = isJSON(response);
                isJson && findMedia(isJson);
            } catch (e) { }
        });
        _xhrOpen.apply(this, arguments);
    };
    try { W.XMLHttpRequest.prototype.open.toString = function () { return _xhrOpen.toString(); }; } catch (e) { }

    function isJSON(str) {
        if (typeof str == "object") {
            return str;
        }
        if (typeof str == "string") {
            try {
                return _JSONparse(str);
            } catch (e) { return false; }
        }
        return false;
    }

    // ===================== indexOf 路径的 m3u8 重拼与发送 =====================
    function parseSendM3U8(m3u8, extItem = undefined) {
        const lines = m3u8.split('\n');
        let out = '';
        for (let i = 0; i < lines.length; i++) {
            if (lines[i].startsWith("#EXT-X-KEY") && lines[i].includes('URI=""')) {
                continue;
            }
            if (lines[i][0] != "#") {
                if (!extItem && !lines[i].startsWith("http")) {
                    return false;
                }
                if (lines[i].startsWith("http")) {
                    out += lines[i] + "\n";
                } else {
                    out += `${extItem.host}/${extItem.path}/${lines[i]}&${extItem.param}\n`;
                }
                continue;
            }
            out += lines[i] + "\n";
            if (lines[i] == "#EXT-X-ENDLIST") { break; }
        }
        sendMediaText(out, "");
    }

    // ===================== 对外调试 API =====================
    try {
        W.__xeHarvest = {
            version: "1.00",
            start: function () { batchStarted = false; maybeStartBatch(); setTimeout(startBatch, 100); },
            items: function () { return [...collectedItems.values()]; },
            keys: function () { return [...keyStore.entries()]; },
            queue: function () { try { return JSON.parse(W.localStorage.getItem(QUEUE_KEY) || "[]"); } catch (e) { return []; } },
            setCfg: function (obj) {
                const cfg = readCfg();
                Object.assign(cfg, obj || {});
                W.localStorage.setItem(CFG_KEY, JSON.stringify(cfg));
                return readCfg();
            },
            getCfg: readCfg,
            dumpQueue: function () { return this.queue(); }
        };
    } catch (e) { }
})();
