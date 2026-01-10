#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import socket
import ssl
import requests
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ================= 基础配置 =================

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

# ================= 日志 =================

def log(msg):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

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

    log("✅ 登录成功，已获取 nz-jwt")

# ================= 获取服务器 =================

def fetch_servers(session):
    url = f"{NEZHA_URL}/api/v1/server"
    log(f"📡 请求服务器接口: {url}")

    r = session.get(url, timeout=10)
    log(f"HTTP 状态码: {r.status_code}")

    if r.status_code != 200:
        raise RuntimeError("服务器接口 HTTP 异常")

    try:
        j = r.json()
    except Exception:
        raise RuntimeError("返回不是 JSON")

    if j.get("error") == "ApiErrorUnauthorized":
        log("🚫 API 返回 ApiErrorUnauthorized（200）")
        raise PermissionError("未授权")

    data = j.get("data")
    if not isinstance(data, list):
        raise RuntimeError("JSON 结构异常")

    log(f"✅ 成功获取服务器列表：{len(data)} 台")
    return data

# ================= TCP 探测 =================

def tcp_latency(ip, port):
    start = time.time()
    try:
        with socket.create_connection((ip, port), timeout=TCP_TIMEOUT):
            return (time.time() - start) * 1000
    except Exception:
        return None

def multi_port_tcp(ip):
    results = []
    for p in TCP_PORTS:
        d = tcp_latency(ip, p)
        if d is not None:
            results.append(d)
    return min(results) if results else None

# ================= TLS 延迟 =================

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

    for k in sorted(data)[:-720]:
        del data[k]

    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    log("📝 延迟数据已记录")

# ================= 图生成 =================

def generate_chart():
    if not DATA_FILE.exists():
        return "暂无数据"

    data = json.loads(DATA_FILE.read_text())
    keys = list(data.keys())[-24:]

    servers = set()
    for v in data.values():
        servers.update(v.keys())

    lines = []
    for s in sorted(servers):
        row = []
        for k in keys:
            v = data.get(k, {}).get(s, 0)
            if v == 0:
                row.append("▁")
            elif v < 50:
                row.append("▂")
            elif v < 100:
                row.append("▃")
            elif v < 200:
                row.append("▄")
            else:
                row.append("█")
        lines.append(f"{s:<15} " + "".join(row))

    lines.append("")
    lines.append("▁=不可达 ▂<50ms ▃<100ms ▄<200ms █≥200ms")
    return "\n".join(lines)

# ================= README =================

def update_readme(chart):
    p = Path(README_FILE)
    content = p.read_text(encoding="utf-8") if p.exists() else ""

    block = (
        f"{START}\n"
        "## 📡 哪吒节点 TCP / TLS 延迟（最近 24 次）\n\n"
        "```\n"
        f"{chart}\n"
        "```\n"
        f"{END}"
    )

    if START in content and END in content:
        new = content.split(START)[0] + block + content.split(END)[1]
    else:
        log("➕ README 中不存在 NEZHA 区块，追加到末尾")
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

    latency_map = {}

    for s in servers:
        name = s.get("name", "unknown")
        ip   = s.get("host", "")
        online = s.get("online", False)

        if not online or not ip:
            latency_map[name] = 0
            log(f"{name}: 离线 延迟=0ms")
            continue

        tcp = multi_port_tcp(ip)
        tls = tls_latency(ip) if tcp is not None else None

        final = tls if tls is not None else (tcp or 0)
        latency_map[name] = round(final, 1)

        log(f"{name}: 在线 TCP={tcp and round(tcp,1)}ms TLS={tls and round(tls,1)}ms")

    record(latency_map)
    update_readme(generate_chart())
    log("🎉 任务完成")

if __name__ == "__main__":
    main()
