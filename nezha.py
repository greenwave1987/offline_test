#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# ================= 基础配置 =================

NEZHA_URL = "https://nz.xmb.cc.cd"
API_SERVER = "/api/v1/server"

NEZHA_USER = os.getenv("NEZHA_USERNAME")
NEZHA_PASS = os.getenv("NEZHA_PASSWORD")
NEZHA_JWT  = os.getenv("NEZHA_JWT")  # 推荐直接使用

README_FILE = "README.md"
DATA_FILE = Path("nezha_latency.json")

TZ = ZoneInfo("Asia/Shanghai")
OFFLINE_SECONDS = 60

START = "<!-- NEZHA-LATENCY-START -->"
END   = "<!-- NEZHA-LATENCY-END -->"

# ================= 日志 =================

def log(msg):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)

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
    log(f"登录返回内容: {r.text[:200]}")

    r.raise_for_status()

    if "nz-jwt" not in session.cookies.get_dict():
        raise RuntimeError("❌ 登录失败：未获取 nz-jwt")

    log("✅ 登录成功，已获取 nz-jwt")

# ================= 获取服务器 =================

def fetch_servers(session):
    url = NEZHA_URL + API_SERVER
    log(f"📡 请求服务器接口: {url}")

    r = session.get(url, timeout=10)
    log(f"HTTP 状态码: {r.status_code}")

    try:
        j = r.json()
    except Exception:
        log("❌ 返回内容不是 JSON")
        log(r.text[:300])
        raise

    # ⚠️ 哪吒的坑：未授权也是 200
    if isinstance(j, dict) and j.get("error") == "ApiErrorUnauthorized":
        log("🚫 API 返回 ApiErrorUnauthorized（200）")
        raise PermissionError("API 未授权")

    if not isinstance(j, dict) or "data" not in j or not isinstance(j["data"], list):
        log("❌ JSON 结构异常")
        log(json.dumps(j, ensure_ascii=False)[:500])
        raise RuntimeError("JSON 结构异常")

    log(f"✅ 成功获取服务器列表：{len(j['data'])} 台")
    return j["data"]

# ================= 在线判断 =================

def is_online(last_active):
    t = datetime.fromisoformat(last_active)
    now = datetime.now(timezone.utc)
    return (now - t.astimezone(timezone.utc)).total_seconds() <= OFFLINE_SECONDS

# ================= TCP 443 延迟 =================

def tcp_latency(ip, port=443, timeout=2):
    try:
        start = time.perf_counter()

        sock = socket.socket(
            socket.AF_INET6 if ":" in ip else socket.AF_INET,
            socket.SOCK_STREAM
        )
        sock.settimeout(timeout)
        sock.connect((ip, port))

        latency = (time.perf_counter() - start) * 1000
        sock.close()

        return round(latency, 1)
    except Exception:
        return 0

# ================= 数据记录 =================

def record_latency(results):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    data = {}
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text())

    data[now] = results

    # 只保留最近 48 次（约 24 小时）
    while len(data) > 48:
        data.pop(next(iter(data)))

    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2)
    )
    log("📝 延迟数据已记录")

# ================= 图表生成 =================

def generate_chart():
    if not DATA_FILE.exists():
        return "暂无数据"

    data = json.loads(DATA_FILE.read_text())
    servers = sorted({k for v in data.values() for k in v})

    lines = []
    for s in servers:
        row = [s.ljust(18)]
        for t in data:
            v = data[t].get(s, 0)
            row.append(
                "▁" if v == 0 else
                "▂" if v < 50 else
                "▃" if v < 100 else
                "▄" if v < 200 else
                "█"
            )
        lines.append(" ".join(row))

    lines.append("")
    lines.append("▁=不可达 ▂<50ms ▃<100ms ▄<200ms █>=200ms")
    return "\n".join(lines)

# ================= README 更新 =================

def update_readme(chart):
    path = Path(README_FILE)
    content = path.read_text(encoding="utf-8")

    block = (
        f"{START}\n"
        "## 🌐 各服务器 TCP 443 延迟趋势\n\n"
        "```\n"
        f"{chart}\n"
        "```\n"
        f"{END}\n"
    )

    if START in content and END in content:
        log("♻️ 检测到 NEZHA 区块，执行替换")
        before = content.split(START)[0]
        after = content.split(END)[1]
        new_content = before + block + after
    else:
        log("➕ README 中不存在 NEZHA 区块，追加到末尾")
        new_content = content.rstrip() + "\n\n" + block

    path.write_text(new_content, encoding="utf-8")
    log("✅ README 更新完成")

# ================= 主流程 =================

def main():
    log("🚀 哪吒 TCP 延迟监控任务启动")

    session = create_session()

    try:
        servers = fetch_servers(session)
    except PermissionError:
        log("♻️ 触发登录流程")
        login(session)
        servers = fetch_servers(session)

    results = {}

    for s in servers:
        name = s.get("name", "unknown").strip()
        ip = (
            s.get("geoip", {}).get("ip", {}).get("ipv4_addr")
            or s.get("geoip", {}).get("ip", {}).get("ipv6_addr")
        )

        online = is_online(s["last_active"])
        latency = tcp_latency(ip) if (online and ip) else 0

        results[name] = latency
        log(f"{name}: {'在线' if online else '离线'} 延迟={latency}ms")

    record_latency(results)
    update_readme(generate_chart())

    log("🎉 任务完成")

if __name__ == "__main__":
    main()
