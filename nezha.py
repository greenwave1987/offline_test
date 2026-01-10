#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ================= 配置 =================

NEZHA_URL = os.getenv("NEZHA_URL", "").rstrip("/")
NEZHA_USER = os.getenv("NEZHA_USERNAME")
NEZHA_PASS = os.getenv("NEZHA_PASSWORD")
NEZHA_JWT  = os.getenv("NEZHA_JWT")  # 推荐直接用

README_FILE = "README.md"
UPTIME_FILE = Path("nezha_uptime.json")

TZ = ZoneInfo("Asia/Shanghai")

START = "<!-- NEZHA-UPTIME-START -->"
END   = "<!-- NEZHA-UPTIME-END -->"

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
    return s

# ================= 登录 =================

def login(session):
    log("🔐 Cookie 失效，尝试登录")

    r = session.post(
        f"{NEZHA_URL}/api/v1/login",
        json={"username": NEZHA_USER, "password": NEZHA_PASS},
        timeout=10
    )

    log(f"登录状态码: {r.status_code}")
    r.raise_for_status()

    if "nz-jwt" not in session.cookies.get_dict():
        raise RuntimeError("登录失败：未获取 nz-jwt")

    log("✅ 登录成功")

# ================= 获取服务器（核心） =================

def fetch_servers(session):
    endpoints = [
        "/api/v1/server/list",
        "/api/v1/servers",
        "/api/v1/monitor",
    ]

    for ep in endpoints:
        url = NEZHA_URL + ep
        log(f"📡 尝试接口 {ep}")

        r = session.get(url, timeout=10)
        log(f"HTTP {r.status_code}")

        if r.status_code in (401, 403):
            raise PermissionError("Cookie 失效")

        if r.status_code != 200:
            continue

        try:
            data = r.json().get("data", [])
        except Exception:
            continue

        if isinstance(data, list) and data:
            log(f"✅ 接口 {ep} 成功，服务器数 {len(data)}")
            return data

    raise RuntimeError("❌ 未发现可用的哪吒服务器接口")

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

    for d in sorted(data)[:-30]:
        del data[d]

    UPTIME_FILE.write_text(json.dumps(data, ensure_ascii=False))
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
        "🟩 在线　🟥 离线\n\n"
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
    log("🚀 哪吒 README 状态任务启动")

    session = create_session()

    try:
        servers = fetch_servers(session)
    except PermissionError:
        login(session)
        servers = fetch_servers(session)

    online = any(s.get("online", True) for s in servers)
    record_hour(online)

    chart = generate_chart()
    update_readme(chart)

    log("🎉 任务完成")

if __name__ == "__main__":
    main()
