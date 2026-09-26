#!/usr/bin/env python3
# kodbox 分享链接上传脚本（七牛直传方案）
# 用法: python3 upload_kodbox.py <文件路径> [文件名]
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.parse

SHARE_ID = "ED9B-U1T"
BASE = "https://pan.jack-sun.com"
COOKIE_FILE = "/tmp/kodbox_cookie.txt"

def block_hash(data: bytes) -> str:
    """复刻 kodbox 前端 blockHash 算法"""
    size = len(data)
    n, e = 50, 200
    if size > e * n:  # 10000 字节
        chunks = []
        o = size // n
        for r in range(n):
            chunks.append(data[o * r: o * r + e])
        chunks.append(data[size - e: size])
        data = b"".join(chunks)
    return hashlib.md5(data).hexdigest() + str(size)

def http_post(url: str, data: dict, headers: dict = None) -> dict:
    body = urllib.parse.urlencode(data).encode()
    h = {"X-Requested-With": "XMLHttpRequest",
         "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
         "User-Agent": "Mozilla/5.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def multipart_post(url: str, fields: dict, file_path: str, field_file: str = "file") -> dict:
    """multipart/form-data 上传到七牛"""
    boundary = "----kodbox" + hashlib.md5(str(time.time()).encode()).hexdigest()
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    fname = os.path.basename(file_path)
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_file}\"; filename=\"{fname}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode())
    with open(file_path, "rb") as f:
        parts.append(f.read())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def get_csrf() -> str:
    """获取 cookie 里的 CSRF_TOKEN"""
    if os.path.exists(COOKIE_FILE):
        for line in open(COOKIE_FILE):
            if "CSRF_TOKEN" in line:
                return line.split()[-1]
    return ""

def upload(file_path: str, name: str = None) -> bool:
    if not name:
        name = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        data = f.read()
    size = len(data)
    md5 = hashlib.md5(data).hexdigest()
    hs = block_hash(data)
    csrf = get_csrf()

    common = {
        "path": "{shareItemLink:" + SHARE_ID + "}/",
        "fullPath": "",
        "name": name,
        "size": str(size),
        "modifyTime": str(int(time.time() * 1000)),
        "chunkSize": "524288",
        "chunks": "0",
        "CSRF_TOKEN": csrf,
        "API_ROUTE": "explorer/share/fileUpload",
    }

    # 1. checkHash 拿七牛上传凭证
    r1 = http_post(f"{BASE}/?explorer/share/fileUpload&shareID={SHARE_ID}",
                   {**common, "checkType": "checkHash", "checkHashSimple": hs})
    if not r1.get("code"):
        print(f"[上传失败] checkHash: {r1.get('data')}")
        return False
    info = r1["info"]["uploadLinkInfo"]
    host, token, key = info["host"], info["token"], info["key"]

    # 2. 直传七牛
    qn = multipart_post(host, {"key": key, "token": token}, file_path)
    if "hash" not in qn:
        print(f"[上传失败] 七牛: {qn}")
        return False

    # 3. 通知 kodbox 入库（uploadLinkSuccess 方式）
    r3 = http_post(f"{BASE}/?explorer/share/fileUpload&shareID={SHARE_ID}", {
        "key": key,
        "size": str(size),
        "name": name,
        "path": "{shareItemLink:" + SHARE_ID + "}/",
        "fullPath": "",
        "paramMore": json.dumps({"hashSimple": hs, "hashMd5": md5}),
        "modifyTime": common["modifyTime"],
        "uploadLinkSuccess": "1",
        "CSRF_TOKEN": csrf,
        "API_ROUTE": "explorer/share/fileUpload",
    })
    if not r3.get("code"):
        print(f"[上传失败] 入库通知: {r3.get('data')}")
        return False
    print(f"[上传成功] {name} ({size} 字节), 七牛key={key}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 upload_kodbox.py <文件路径> [文件名]")
        sys.exit(1)
    name = sys.argv[2] if len(sys.argv) > 2 else None
    ok = upload(sys.argv[1], name)
    sys.exit(0 if ok else 1)
