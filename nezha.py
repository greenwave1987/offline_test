#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import socket
import ssl
import hashlib
import requests
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ================= 配置 =================

NEZHA_URL = os.getenv("NEZHA_URL", "").rstrip("/")
NEZHA_USER = os.getenv("NEZHA_USERNAME")
NEZHA_PASS = os.getenv("NEZHA_PASSWORD")
NEZHA_JWT  = os.getenv("NEZHA_JWT")

README_FILE = "README.md"
DATA_FILE   = Path("nezha_latency.json")

TZ = ZoneInfo("Asia/Shanghai")

START = "<!-- NEZHA-LATENCY-START -->"
END   = "<!-- NEZHA-LATENCY-END -->"

TCP_PORTS = [443, 80, 22]
TCP_TIMEOUT = 3
TLS_TIMEOUT = 4

OFFLINE_THRESHOLD = 600
MAX_POINTS = 24

# ================= 日志 =================

def log(msg):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

# ================= 时间解析 =================

def parse_last_active(v):
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        try:
            return int(datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp())
        except Exception:
            return 0
    return 0

# ================= Session =================

def create_session():
    s = requests.Session()
    if NEZHA_JWT:
        s.cookies.set("nz-jwt", NEZHA_JWT)
        log("🍪 使用 nz-jwt Cookie")
    else:
        log("⚠️ 未提供 nz-jwt，将尝试登录")
    return s

# ================= 登录 =================

def login(session):
    log("🔐 开始登录哪吒面板")
    r = session.post(
        f"{NEZHA_URL}/api/v1/login",
        json={"username": NEZHA_USER, "password": NEZHA_PASS},
        timeout=10
    )
    log(f"登录 HTTP 状态码: {r.status_code}")
    log(f"登录返回内容: {r.text[:100]}")
    r.raise_for_status()
    if "nz-jwt" not in session.cookies.get_dict():
        raise RuntimeError("登录失败")
    log("✅ 登录成功")

# ================= API =================

def fetch_servers(session):
    r = session.get(f"{NEZHA_URL}/api/v1/server", timeout=10)
    log(f"HTTP 状态码: {r.status_code}")
    j = r.json()
    if j.get("error") == "ApiErrorUnauthorized":
        raise PermissionError
    data = j.get("data", [])
    log(f"✅ 成功获取服务器列表：{len(data)} 台")
    return data

# ================= 探测 =================

def tcp_latency(host, port):
    """TCP 延迟测量"""
    start = time.time()
    try:
        with socket.create_connection((host, port), timeout=TCP_TIMEOUT):
            elapsed = (time.time() - start) * 1000
            return round(elapsed, 1)
    except Exception:
        return None  # 失败返回 None

def multi_tcp(host):
    """测量多个 TCP 端口，返回最小延迟"""
    vals = []
    for p in TCP_PORTS:
        d = tcp_latency(host, p)
        log(f"🌐 {host} TCP {p} 延迟: {d}ms")
        if d is not None:
            vals.append(d)
    return min(vals) if vals else None

def tls_latency(host, server_name):
    """TLS 延迟测量"""
    ctx = ssl.create_default_context()
    start = time.time()
    try:
        with socket.create_connection((host, 443), timeout=TCP_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=server_name):
                elapsed = (time.time() - start) * 1000
                return round(elapsed, 1)
    except Exception:
        return None

# ================= 数据 =================

def record(lat_map):
    ts = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    data = {}
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text())
    data[ts] = lat_map
    for k in sorted(data)[:-MAX_POINTS]:
        del data[k]
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    log("📝 延迟数据已记录")

# ================= SVG =================

def color_for(name):
    return "#" + hashlib.md5(name.encode()).hexdigest()[:6]

def generate_svg():
    if not DATA_FILE.exists():
        return "暂无数据"

    data = json.loads(DATA_FILE.read_text())
    keys = list(data.keys())
    servers = sorted({s for v in data.values() for s in v})

    w, h, p = 720, 260, 40
    maxv = max((v for d in data.values() for v in d.values()), default=100)
    maxv = max(maxv, 100)

    def x(i): return p + i * (w - 2*p) / max(len(keys)-1, 1)
    def y(v): return h - p - v * (h - 2*p) / maxv

    svg = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">']
    svg += [
        f'<line x1="{p}" y1="{p}" x2="{p}" y2="{h-p}" stroke="#888"/>',
        f'<line x1="{p}" y1="{h-p}" x2="{w-p}" y2="{h-p}" stroke="#888"/>'
    ]

    for s in servers:
        pts = [f"{x(i)},{y(data[k].get(s,0))}" for i,k in enumerate(keys)]
        svg.append(
            f'<polyline fill="none" stroke="{color_for(s)}" stroke-width="2" points="{" ".join(pts)}"/>'
        )

    lx, ly = p, p-10
    for s in servers:
        svg.append(f'<text x="{lx}" y="{ly}" font-size="10" fill="{color_for(s)}">{s}</text>')
        lx += len(s)*7 + 12

    svg.append("</svg>")
    return "\n".join(svg)

# ================= README =================

def update_readme(svg):
    p = Path(README_FILE)
    content = p.read_text(encoding="utf-8") if p.exists() else ""
    block = f"{START}\n## 📈 哪吒节点 TCP / TLS 延迟\n\n{svg}\n{END}"
    if START in content and END in content:
        content = content.split(START)[0] + block + content.split(END)[1]
    else:
        content += "\n\n" + block
    p.write_text(content, encoding="utf-8")
    log("✅ README 更新完成")

# ================= 主程序 =================

def main():
    session = create_session()
    try:
        servers = fetch_servers(session)
    except PermissionError:
        login(session)
        servers = fetch_servers(session)

    now = int(time.time())
    lat_map = {}

    for s in servers:
        name = s.get("name","unknown")
        last = parse_last_active(s.get("last_active"))

        host = (
            s.get("public_ip")
            or s.get("ipv4")
            or s.get("ipv6")
            or s.get("host")
        )

        if not host or now - last > OFFLINE_THRESHOLD:
            lat_map[name] = 0
            log(f"{name}: 离线")
            continue

        tcp = multi_tcp(host)
        tls = tls_latency(host, s.get("host") or host)

        # 优先使用 TLS，如果 TLS 不可达则使用 TCP
        val = round(tls if tls is not None else tcp if tcp is not None else 0, 1)
        lat_map[name] = val

        log(f"{name}: {val}ms")

    record(lat_map)
    update_readme(generate_svg())
    log("🎉 任务完成")

if __name__ == "__main__":
    main()
