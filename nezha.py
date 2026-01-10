#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ================= 配置 =================

NEZHA_URL = os.getenv("NEZHA_URL", "").rstrip("/")
NEZHA_USER = os.getenv("NEZHA_USERNAME")
NEZHA_PASS = os.getenv("NEZHA_PASSWORD")

README_FILE = "README.md"
UPTIME_FILE = Path("nezha_uptime.json")

TZ = ZoneInfo("Asia/Shanghai")
OFFLINE_THRESHOLD = 60  # 秒

START = "<!-- NEZHA-UPTIME-START -->"
END   = "<!-- NEZHA-UPTIME-END -->"

# ================= 日志 =================

def log(msg):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

# ================= Session =================

def create_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (GitHub Actions)",
        "Accept": "application/json"
    })
    return s

# ================= 登录 =================

def login(session):
    log("🔐 开始登录哪吒面板")
    log(f"POST {NEZHA_URL}/api/v1/login")

    r = session.post(
        f"{NEZHA_URL}/api/v1/login",
        json={
            "username": NEZHA_USER,
            "password": NEZHA_PASS
        },
        timeout=15
    )

    log(f"登录 HTTP 状态码: {r.status_code}")
    r.raise_for_status()

    cookies = session.cookies.get_dict()
    log(f"🍪 登录后 Cookies: {cookies}")

    if "nz-jwt" not in cookies:
        raise RuntimeError("❌ 登录失败：未获取 nz-jwt")

    log("✅ 登录成功")

# ================= 获取服务器 =================

def fetch_servers(session):
    url = f"{NEZHA_URL}/api/v1/server"
    log(f"📡 请求服务器接口: {url}")

    r = session.get(url, timeout=15)
    log(f"HTTP 状态码: {r.status_code}")
    r.raise_for_status()

    payload = r.json()

    if not payload.get("success") or "data" not in payload:
        raise RuntimeError("❌ JSON 结构异常")

    servers = payload["data"]
    log(f"📊 服务器总数: {len(servers)}")

    return servers

# ================= 在线判断 =================

def is_online(server, now):
    last_active_str = server.get("last_active")
    if not last_active_str:
        return False

    last_active = datetime.fromisoformat(last_active_str)
    diff = (now - last_active).total_seconds()

    return diff <= OFFLINE_THRESHOLD

# ================= 记录在线 =================

def record_hour(online):
    now = datetime.now(TZ)
    day = now.strftime("%Y-%m-%d")
    hour = now.strftime("%H")

    data = {}
    if UPTIME_FILE.exists():
        data = json.loads(UPTIME_FILE.read_text())

    data.setdefault(day, {})
    data[day][hour] = 1 if online else 0

    # 只保留 30 天
    for d in sorted(data)[:-30]:
        del data[d]

    UPTIME_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2)
    )

    log(f"📝 记录 {day} {hour}: {'在线' if online else '离线'}")

# ================= 生成图 =================

def generate_chart():
    if not UPTIME_FILE.exists():
        return "暂无数据"

    data = json.loads(UPTIME_FILE.read_text())
    days = sorted(data)[-30:]

    lines = []
    for h in range(23, -1, -1):
        row = []
        for d in days:
            v = data.get(d, {}).get(f"{h:02d}", 0)
            row.append("🟩" if v else "🟥")
        lines.append(f"{h:02d}  " + " ".join(row))

    lines.append("")
    lines.append("     " + " ".join(days))
    return "\n".join(lines)

# ================= 更新 README =================

def update_readme(chart):
    content = Path(README_FILE).read_text(encoding="utf-8")

    block = (
        f"{START}\n"
        "## 📈 最近 30 天在线状态（每小时）\n\n"
        "🟩 在线　🟥 离线（last_active 超过 60 秒）\n\n"
        "```\n"
        f"{chart}\n"
        "```\n"
        f"{END}"
    )

    if START in content and END in content:
        new = content.split(START)[0] + block + content.split(END)[1]
    else:
        new = content.rstrip() + "\n\n" + block

    Path(README_FILE).write_text(new, encoding="utf-8")
    log("✅ README 已更新")

# ================= 主入口 =================

def main():
    log("🚀 哪吒 README 状态任务启动")

    session = create_session()
    login(session)

    servers = fetch_servers(session)

    now = datetime.now(TZ)

    online_servers = []
    offline_servers = []

    for s in servers:
        name = s.get("name", "unknown")
        if is_online(s, now):
            online_servers.append(name)
            log(f"🟢 在线: {name}")
        else:
            offline_servers.append(name)
            log(f"🔴 离线: {name}")

    overall_online = len(online_servers) > 0
    log(f"📊 在线 {len(online_servers)} / 离线 {len(offline_servers)}")

    record_hour(overall_online)

    chart = generate_chart()
    update_readme(chart)

    log("🎉 任务完成")

if __name__ == "__main__":
    main()
