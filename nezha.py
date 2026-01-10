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

OFFLINE_THRESHOLD = 600      # 秒
MAX_POINTS = 24              # 曲线点数

# ================= 日志 =================

def log(msg):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

# ================= 时间解析 =================

def parse_last_active(v):
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return int(dt.timestamp())
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
    log(f"登录返回内容: {r.text[:120]}")
    r.raise_for_status()

    if "nz-jwt" not in session.cookies.get_dict():
        raise RuntimeError("登录失败：未获取 nz-jwt")

    log("✅ 登录成功")

# ================= 获取服务器 =================

def fetch_servers(session):
    url = f"{NEZHA_URL}/api/v1/server"
    log(f"📡 请求服务器接口: {url}")

    r = session.get(url, timeout=10)
    log(f"HTTP 状态码: {r.status_code}")

    j = r.json()
    if j.get("error") == "ApiErrorUnauthorized":
        raise PermissionError

    data = j.get("data")
    if not isinstance(data, list):
        raise RuntimeError("JSON 结构异常")

    log(f"✅ 成功获取服务器列表：{len(data)} 台")
    return data

# ================= TCP / TLS =================

def tcp_latency(ip, port):
    start = time.time()
    try:
        with socket.create_connection((ip, port), timeout=TCP_TIMEOUT):
            return (time.time() - start) * 1000
    except Exception:
        return None

def multi_port_tcp(ip):
    vals = []
    for p in TCP_PORTS:
        d = tcp_latency(ip, p)
        if d is not None:
            vals.append(d)
    return min(vals) if vals else None

def tls_latency(ip):
    ctx = ssl.create_default_context()
    start = time.time()
    try:
        with socket.create_connection((ip, 443), timeout=TCP_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=ip):
                return (time.time() - start) * 1000
    except Exception:
        return None

# ================= 数据记录 =================

def record(latency_map):
    ts = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    data = {}
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text())

    data[ts] = latency_map

    for k in sorted(data)[:-MAX_POINTS]:
        del data[k]

    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    log("📝 延迟数据已记录")

# ================= 颜色 =================

def color_for(name):
    h = hashlib.md5(name.encode()).hexdigest()
    return f"#{h[:6]}"

# ================= SVG 曲线 =================

def generate_svg():
    if not DATA_FILE.exists():
        return "暂无数据"

    data = json.loads(DATA_FILE.read_text())
    keys = list(data.keys())[-MAX_POINTS:]

    servers = sorted({s for v in data.values() for s in v})

    width = 720
    height = 260
    padding = 40

    max_latency = max(
        (v for d in data.values() for v in d.values()),
        default=100
    )
    max_latency = max(max_latency, 100)

    svg = [
        f'<svg width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
    ]

    # 轴线
    svg.append(f'<line x1="{padding}" y1="{padding}" '
               f'x2="{padding}" y2="{height-padding}" stroke="#888"/>')
    svg.append(f'<line x1="{padding}" y1="{height-padding}" '
               f'x2="{width-padding}" y2="{height-padding}" stroke="#888"/>')

    def x(i):
        return padding + i * (width - 2*padding) / (len(keys)-1 or 1)

    def y(v):
        return height - padding - v * (height - 2*padding) / max_latency

    for name in servers:
        pts = []
        for i, k in enumerate(keys):
            v = data.get(k, {}).get(name, 0)
            pts.append(f"{x(i)},{y(v)}")

        svg.append(
            f'<polyline fill="none" '
            f'stroke="{color_for(name)}" '
            f'stroke-width="2" '
            f'points="{" ".join(pts)}"/>'
        )

    # 图例
    lx = padding
    ly = padding - 10
    for name in servers:
        svg.append(
            f'<text x="{lx}" y="{ly}" font-size="10" '
            f'fill="{color_for(name)}">{name}</text>'
        )
        lx += len(name) * 7 + 14

    svg.append("</svg>")
    return "\n".join(svg)

# ================= README =================

def update_readme(svg):
    p = Path(README_FILE)
    content = p.read_text(encoding="utf-8") if p.exists() else ""

    block = (
        f"{START}\n"
        "## 📈 哪吒节点 TCP / TLS 延迟曲线\n\n"
        f"{svg}\n"
        f"{END}"
    )

    if START in content and END in content:
        new = content.split(START)[0] + block + content.split(END)[1]
    else:
        new = content + "\n\n" + block

    p.write_text(new, encoding="utf-8")
    log("✅ README 更新完成")

# ================= 主入口 =================

def main():
    log("🚀 哪吒 TCP + TLS 延迟监控任务启动")

    session = create_session()
    try:
        servers = fetch_servers(session)
    except PermissionError:
        log("♻️ 触发登录流程")
        login(session)
        servers = fetch_servers(session)

    now_ts = int(time.time())
    latency_map = {}

    for s in servers:
        name = s.get("name", "unknown").strip()
        ip   = s.get("host")
        last = parse_last_active(s.get("last_active"))

        if not ip or now_ts - last > OFFLINE_THRESHOLD:
            latency_map[name] = 0
            log(f"{name}: 离线")
            continue

        tcp = multi_port_tcp(ip)
        tls = tls_latency(ip) if tcp else None
        latency_map[name] = round(tls or tcp or 0, 1)

        log(f"{name}: TCP={tcp and round(tcp,1)}ms TLS={tls and round(tls,1)}ms")

    record(latency_map)
    update_readme(generate_svg())
    log("🎉 任务完成")

if __name__ == "__main__":
    main()
