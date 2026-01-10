#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import re
import requests
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ================= 基础配置 =================

NEZHA_URL = os.getenv("NEZHA_URL", "").rstrip("/")
NEZHA_USER = os.getenv("NEZHA_USERNAME")
NEZHA_PASS = os.getenv("NEZHA_PASSWORD")
NEZHA_JWT  = os.getenv("NEZHA_JWT")  # 可选，优先使用

README_FILE = "README.md"
UPTIME_FILE = Path("nezha_uptime.json")

TZ = ZoneInfo("Asia/Shanghai")

START_MARK = "<!-- NEZHA-UPTIME-START -->"
END_MARK   = "<!-- NEZHA-UPTIME-END -->"

# ================= 日志 =================

def log(msg):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

# ================= 会话 =================

def create_session():
    s = requests.Session()
    if NEZHA_JWT:
        s.cookies.set("nz-jwt", NEZHA_JWT)
        log("🍪 已注入 nz-jwt Cookie")
    return s

# ================= 登录 =================

def login(session: requests.Session):
    log("🔐 Cookie 无效，尝试登录")

    if not NEZHA_USER or not NEZHA_PASS:
        raise RuntimeError("缺少 NEZHA_USERNAME / NEZHA_PASSWORD")

    r = session.post(
        f"{NEZHA_URL}/api/v1/login",
        json={"username": NEZHA_USER, "password": NEZHA_PASS},
        timeout=10
    )

    log(f"登录 HTTP 状态码: {r.status_code}")
    r.raise_for_status()

    if "nz-jwt" not in session.cookies.get_dict():
        raise RuntimeError("登录成功但未获取 nz-jwt")

    log("✅ 登录成功，已刷新 Cookie")

# ================= 获取服务器列表（核心） =================

def fetch_servers(session: requests.Session):
    log("📡 请求服务器列表")

    # ---- ① 优先尝试 JSON 接口（新版本哪吒） ----
    r = session.get(f"{NEZHA_URL}/api/v1/server/list", timeout=10)
    log(f"/server/list HTTP 状态码: {r.status_code}")

    if r.status_code == 200:
        data = r.json().get("data", [])
        log(f"📊 JSON 接口服务器数量: {len(data)}")
        return data

    if r.status_code in (401, 403):
        raise PermissionError("Cookie 失效")

    # ---- ② 回退 HTML 页面接口（你当前这个面板） ----
    log("↩️ JSON 接口不存在，回退到 /api/v1/server")

    r = session.get(f"{NEZHA_URL}/api/v1/server", timeout=10)
    log(f"/server HTTP 状态码: {r.status_code}")

    if r.status_code in (401, 403):
        raise PermissionError("Cookie 失效")

    r.raise_for_status()

    html = r.text

    # ---- ③ 解析前端注入的 INITIAL_STATE ----
    m = re.search(
        r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        html,
        re.S
    )

    if not m:
        raise RuntimeError("无法从 HTML 中解析服务器数据")

    state = json.loads(m.group(1))
    servers = state.get("server", {}).get("servers", [])

    log(f"📊 HTML 页面解析服务器数量: {len(servers)}")
    return servers

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

    # 仅保留最近 30 天
    for d in sorted(data.keys())[:-30]:
        del data[d]

    UPTIME_FILE.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8"
    )

    log(f"📝 记录 {day} {hour}:00 → {'在线' if is_online else '离线'}")

# ================= 生成 30×24 热力图 =================

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

def update_readme(chart: str):
    log("🧾 更新 README")

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

    new_content = (
        content.split(START_MARK)[0]
        + block
        + content.split(END_MARK)[1]
    )

    Path(README_FILE).write_text(new_content, encoding="utf-8")
    log("✅ README 更新完成")

# ================= 主流程 =================

def main():
    log("🚀 哪吒 README 状态任务启动")

    session = create_session()

    try:
        servers = fetch_servers(session)
    except PermissionError:
        login(session)
        servers = fetch_servers(session)

    log(f"📊 服务器总数: {len(servers)}")

    offline = [s for s in servers if not s.get("online", True)]
    log(f"🚨 离线服务器数量: {len(offline)}")

    any_online = any(s.get("online", True) for s in servers)

    record_hour_status(any_online)

    chart = generate_uptime_heatmap()
    update_readme(chart)

    log("🎉 任务完成")

if __name__ == "__main__":
    main()
