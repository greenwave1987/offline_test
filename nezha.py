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
NEZHA_JWT  = os.getenv("NEZHA_JWT")  # 可选，推荐

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
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (GitHub Actions)",
        "Accept": "application/json"
    })

    if NEZHA_JWT:
        s.cookies.set("nz-jwt", NEZHA_JWT)
        log("🍪 已注入 nz-jwt Cookie")

    return s

# ================= 登录 =================

def login(session):
    log("🔐 开始登录哪吒面板")
    log(f"POST {NEZHA_URL}/api/v1/login")

    payload = {
        "username": NEZHA_USER,
        "password": NEZHA_PASS
    }

    r = session.post(
        f"{NEZHA_URL}/api/v1/login",
        json=payload,
        timeout=15
    )

    log(f"登录 HTTP 状态码: {r.status_code}")
    r.raise_for_status()

    cookies = session.cookies.get_dict()
    log(f"🍪 当前 Cookies: {cookies}")

    if "nz-jwt" not in cookies:
        raise RuntimeError("❌ 登录失败：未获取 nz-jwt")

    log("✅ 登录成功，nz-jwt 已获取")

# ================= 获取服务器（唯一接口） =================

def fetch_servers(session):
    url = f"{NEZHA_URL}/api/v1/server"
    log(f"📡 请求服务器接口: {url}")

    r = session.get(url, timeout=15)
    log(f"HTTP 状态码: {r.status_code}")

    if r.status_code in (401, 403):
        raise PermissionError("Cookie 无效或过期")

    r.raise_for_status()

    # 🚨 强制 JSON
    try:
        payload = r.json()
    except Exception as e:
        log("❌ 返回内容不是 JSON")
        raise RuntimeError("接口返回非 JSON") from e

    if not isinstance(payload, dict) or "data" not in payload:
        raise RuntimeError("JSON 结构异常")

    servers = payload["data"]

    if not isinstance(servers, list):
        raise RuntimeError("服务器数据不是列表")

    log(f"📊 服务器总数: {len(servers)}")
    offline = sum(1 for s in servers if not s.get("online", True))
    log(f"🚨 离线服务器数: {offline}")

    return servers

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

    log(f"📝 记录在线状态 {day} {hour}: {'在线' if online else '离线'}")

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

    try:
        servers = fetch_servers(session)
    except PermissionError:
        log("⚠️ Cookie 失效，准备登录")
        login(session)
        servers = fetch_servers(session)

    online = any(s.get("online", True) for s in servers)
    record_hour(online)

    chart = generate_chart()
    update_readme(chart)

    log("🎉 任务完成")

if __name__ == "__main__":
    main()
