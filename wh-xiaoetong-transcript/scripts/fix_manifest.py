"""
wh-xiaoetong-transcript 扩展 manifest MV3 兼容修复
==================================================
清理非商店 crx 解压版 manifest 的 MV2 遗留权限：
  1) 删除 "webRequestBlocking"（报错: requires manifest version of 2 or lower）
  2) "chrome://favicon/" -> "favicon"（报错: Permission 'chrome://favicon/' is unknown）

用法: python scripts/fix_manifest.py --dir "download/extracted/tampermonkey"
      python scripts/fix_manifest.py --dir "download/extracted/catcatch"  (通常无需改)
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path


def fix_manifest(ext_dir: Path) -> dict:
    mf = ext_dir / "manifest.json"
    if not mf.exists():
        raise SystemExit(f"[错误] 无 manifest.json: {mf}")

    data = json.loads(mf.read_text(encoding="utf-8"))
    before = json.dumps(data, ensure_ascii=False)
    changed = []

    # 1) 删除 webRequestBlocking 权限
    perms = data.get("permissions", [])
    if "webRequestBlocking" in perms:
        perms.remove("webRequestBlocking")
        data["permissions"] = perms
        changed.append("webRequestBlocking")

    # 2) chrome://favicon/ -> favicon
    perms = data.get("permissions", [])
    for i, p in enumerate(perms):
        if p == "chrome://favicon/":
            perms[i] = "favicon"
            changed.append("chrome://favicon/ -> favicon")
            data["permissions"] = perms

    # 可选: 处理 "webRequest" 权限中的 "blocking" 特殊权限（MV3 需 declarativeNetRequest）
    # 此处仅处理已知的两个错误，其余保留。

    after = json.dumps(data, ensure_ascii=False)
    if before == after:
        return {"changed": [], "needs_reload": False}

    # 归档原文件
    backup = mf.parent / f"manifest.json.bak-{time.strftime('%Y%m%d%H%M%S')}"
    shutil.copy2(str(mf), str(backup))

    # 写回
    mf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 校验
    json.loads(mf.read_text(encoding="utf-8"))
    return {"changed": changed, "backup": str(backup), "needs_reload": True}


def main():
    ap = argparse.ArgumentParser(description="manifest MV3 兼容修复")
    ap.add_argument("--dir", required=True, help="扩展解压目录（含 manifest.json）")
    args = ap.parse_args()

    r = fix_manifest(Path(args.dir))
    if not r["changed"]:
        print(f"[OK] {args.dir} 无需修改（manifest 已 MV3 兼容）")
        return
    print(f"[已修复] {args.dir}")
    for c in r["changed"]:
        print(f"  - {c}")
    print(f"  备份: {r['backup']}")
    print("请到 chrome://extensions 点该扩展【重新加载】。")


if __name__ == "__main__":
    main()
