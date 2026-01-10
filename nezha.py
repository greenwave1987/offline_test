#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ================= 基础配置 =================

NEZHA_URL = os.getenv("NEZHA_URL")          # https://nz.example.com
NEZHA_USER = os.getenv("NEZHA_USERNAME")
NEZHA_PASS = os.getenv("NEZHA_PASSWORD")

README_FILE = "README.md"
UPTIME_FILE = Path("nezha_uptime.json")

TZ = ZoneInfo("Asia/Shanghai")

START_MARK = "<!-- NEZHA-UPTIME-START -->"
END_MARK = "<!-- NEZHA-UPTIME-END -->"

# ================= 日志 =================

def log(msg):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

# ================= 登录 =================

def nezha_login():
    log("🔐 正在登录哪吒面板")

    url = f"{NEZHA_URL}/api/v1/login"
    payload = {
        "username": NEZHA_USER,
        "password": NEZHA_PASS
    }

    r = requests.post(url, json=payload, timeout=10)
    log(f"HTTP 状态码: {r.status_code}")

    r.raise_for_status()

    cookies = r.cookies.get_dict()
    if "nz-jwt" not in cookies:
        raise RuntimeError("未获取到 nz-jwt")

    log("✅ 登录成功")
    return cookies["nz-jwt"]

# ================= 获取服务器 =================

def fetch_servers(jwt):
    log("📡 请求服务器列表 API")

    url = f"{NEZHA_URL}/api/v1/server/list"
    headers = {
        "cookie": jwt
    }

    r = requests.get(url, headers=headers, timeout=10)
    log(f"HTTP 状态码: {r.status_code}")
    r.raise_for_status()

    data = r.json().get("data", [])
    log(f"📊 服务器总数: {len(data)}")
    return data

# ================= 记录小时状态 =================

def record_hour_status(is_online: bool):
    now = datetime.now(TZ)
    day = now.strftime("%Y-%m-%d")
    hour = now.strftime("%H")

    data = {}
    if UPTIME_FILE.exists():
        data = json.loads(UPTIME_FILE.read_text(encoding="utf-8"))

    data.setdefault(day, {})
    data[day][hour] = 1 if is_online else 0

    # 只保留最近 30 天
    for d in sorted(data.keys())[:-30]:
        del data[d]

    UPTIME_FILE.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8"
    )

    log(f"📝 记录 {day} {hour}:00 状态 → {'在线' if is_online else '离线'}")

# ================= 生成 30 天 × 24 小时 图 =================

def generate_uptime_heatmap():
    if not UPTIME_FILE.exists():
        return "暂无数据"

    data = json.loads(UPTIME_FILE.read_text(encoding="utf-8"))
    days = sorted(data.keys())[-30:]

    lines = []

    for h in range(23, -1, -1):
        hour = f"{h:02d}"
        row = []
        for d in days:
            v = data.get(d, {}).get(hour, 0)
            row.append("🟩" if v == 1 else "🟥")
        lines.append(f"{hour}  " + " ".join(row))

    footer = "     " + " ".join(days)

    return "\n".join(lines + ["", footer])

# ================= 更新 README =================

def update_readme(chart):
    log("🧾 更新 README 在线状态图")

    if not Path(README_FILE).exists():
        raise RuntimeError("README.md 不存在")

    content = Path(README_FILE).read_text(encoding="utf-8")

    if START_MARK not in content or END_MARK not in content:
        raise RuntimeError("README 中缺少 NEZHA 标记区块")

    block = (
        f"{START_MARK}\n"
        "## 📈 最近 30 天在线热力图（每小时）\n\n"
        "🟩 在线 🟥 离线\n\n"
        "```\n"
        f"{chart}\n"
        "```\n"
        f"{END_MARK}"
    )

    new_content = content.split(START_MARK)[0] + block + content.split(END_MARK)[1]
    Path(README_FILE).write_text(new_content, encoding="utf-8")

    log("✅ README 更新完成")

# ================= 主流程 =================

def main():
    log("🚀 哪吒 README 状态任务启动")

    jwt = nezha_login()
    servers = fetch_servers(jwt)

    offline = [s for s in servers if not s.get("online", True)]
    log(f"🚨 离线服务器数量: {len(offline)}")

    any_online = any(s.get("online", True) for s in servers)

    record_hour_status(any_online)

    chart = generate_uptime_heatmap()
    update_readme(chart)

    log("🎉 任务完成")

if __name__ == "__main__":
    main()
