#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

# ================= 基础配置 =================

NEZHA_URL = "https://nz.xmb.cc.cd"
API_SERVER = "/api/v1/server"

NEZHA_USER = os.getenv("NEZHA_USERNAME")
NEZHA_PASS = os.getenv("NEZHA_PASSWORD")
NEZHA_JWT  = os.getenv("NEZHA_JWT")   # 优先使用

README_FILE = "README.md"
DATA_FILE   = Path("nezha_latency.json")

TZ = ZoneInfo("Asia/Shanghai")

START = "<!-- NEZHA-LATENCY-START -->"
END   = "<!-- NEZHA-LATENCY-END -->"

OFFLINE_SECONDS = 60   # 超过 60 秒视为掉线

# ================= 日志 =================

def log(msg):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

# ================= Session =================

def create_session():
    s = requests.Session()
    if NEZHA_JWT:
        s.cookies.set("nz-jwt", NEZHA_JWT)
        log("🍪 已注入 nz-jwt Cookie")
    return s

# ================= 登录 =================

def login(session):
    log("🔐 Cookie 失效，开始账号密码登录")

    r = session.post(
        f"{NEZHA_URL}/api/v1/login",
        json={"username": NEZHA_USER, "password": NEZHA_PASS},
        timeout=10
    )

    log(f"登录 HTTP 状态码: {r.status_code}")
    r.raise_for_status()

    if "nz-jwt" not in session.cookies.get_dict():
        raise RuntimeError("❌ 登录失败，未获取 nz-jwt")

    log("✅ 登录成功，已获得 nz-jwt")

# ================= 获取服务器 =================

def fetch_servers(session):
    url = NEZHA_URL + API_SERVER
    log(f"📡 请求服务器接口: {url}")

    r = session.get(url, timeout=10)
    log(f"HTTP 状态码: {r.status_code}")

    if r.status_code in (401, 403):
        raise PermissionError("Cookie 失效")

    r.raise_for_status()

    j = r.json()
    if not isinstance(j, dict) or "data" not in j:
        raise RuntimeError("JSON 结构异常")

    log(f"✅ 成功获取服务器列表，共 {len(j['data'])} 台")
    return j["data"]

# ================= 在线判断 =================

def is_online(last_active_str):
    last = datetime.fromisoformat(last_active_str)
    now = datetime.now(timezone.utc)
    diff = (now - last.astimezone(timezone.utc)).total_seconds()
    return diff <= OFFLINE_SECONDS

# ================= Ping 延迟 =================

def ping_latency(ip):
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        if r.returncode != 0:
            return 0

        for line in r.stdout.splitlines():
            if "time=" in line:
                return float(line.split("time=")[1].split(" ")[0])
    except Exception:
        pass

    return 0

# ================= 记录延迟 =================

def record_latency(results):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    data = {}
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text())

    data[now] = results

    # 保留最近 48 条
    while len(data) > 48:
        data.pop(next(iter(data)))

    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    log("📝 延迟数据已记录")

# ================= 生成曲线（文本） =================

def generate_chart():
    if not DATA_FILE.exists():
        return "暂无数据"

    data = json.loads(DATA_FILE.read_text())
    servers = set()

    for v in data.values():
        servers |= set(v.keys())

    lines = []
    for name in sorted(servers):
        line = [name.ljust(16)]
        for t in data:
            v = data[t].get(name, 0)
            if v == 0:
                line.append("▁")
            elif v < 50:
                line.append("▂")
            elif v < 100:
                line.append("▃")
            elif v < 200:
                line.append("▄")
            else:
                line.append("█")
        lines.append(" ".join(line))

    lines.append("")
    lines.append("时间 → " + " ".join(data.keys()))
    lines.append("▁=0ms  ▂<50  ▃<100  ▄<200  █>=200")

    return "\n".join(lines)

# ================= 更新 README =================

def update_readme(chart):
    content = Path(README_FILE).read_text(encoding="utf-8")

    block = (
        f"{START}\n"
        "## 🌐 各服务器延迟曲线（Ping）\n\n"
        "```\n"
        f"{chart}\n"
        "```\n"
        f"{END}"
    )

    new = content.split(START)[0] + block + content.split(END)[1]
    Path(README_FILE).write_text(new, encoding="utf-8")
    log("✅ README 已更新")

# ================= 主入口 =================

def main():
    log("🚀 哪吒延迟监控任务启动")

    session = create_session()

    try:
        servers = fetch_servers(session)
    except PermissionError:
        login(session)
        servers = fetch_servers(session)

    results = {}

    for s in servers:
        name = s.get("name", "unknown").strip()
        ip = (
            s.get("geoip", {})
             .get("ip", {})
             .get("ipv4_addr")
            or s.get("geoip", {})
                 .get("ip", {})
                 .get("ipv6_addr")
        )

        if not ip:
            results[name] = 0
            continue

        online = is_online(s["last_active"])
        latency = ping_latency(ip) if online else 0

        results[name] = latency
        log(f"{name}: {'在线' if online else '离线'} 延迟 {latency} ms")

    record_latency(results)

    chart = generate_chart()
    update_readme(chart)

    log("🎉 任务完成")

if __name__ == "__main__":
    main()
