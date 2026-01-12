#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
import base64

# ================= 配置 =================
NEZHA_URL = os.getenv("NEZHA_URL", "").rstrip("/")
NEZHA_USER = os.getenv("NEZHA_USERNAME")
NEZHA_PASS = os.getenv("NEZHA_PASSWORD")
NEZHA_JWT = os.getenv("NEZHA_JWT")
GH_TOKEN = os.getenv("GH_TOKEN")
TZ = ZoneInfo("Asia/Shanghai")

SERVER_TO_REPO = {
    "galaxy-02": "greenwave1987/galaxy2",
    "galaxy-03": "greenwave1987/galaxy3"
}

# ================= 日志 =================
def log(msg):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

# ================= Session =================
def create_session():
    log("🟢 创建 Session")
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
    log(f"登录返回状态码: {r.status_code}")
    r.raise_for_status()
    if "nz-jwt" not in session.cookies.get_dict():
        raise RuntimeError("登录失败")
    log("✅ 登录成功")

# ================= 获取服务器列表 =================
def fetch_servers(session):
    log("🌐 获取服务器列表")
    r = session.get(f"{NEZHA_URL}/api/v1/server", timeout=10)
    log(f"获取返回状态码: {r.status_code}")
    r.raise_for_status()
    j = r.json()
    if j.get("error") == "ApiErrorUnauthorized":
        raise PermissionError
    servers = j.get("data", [])
    log(f"📃 获取到 {len(servers)} 台服务器")
    return servers

# ================= 修改 GitHub README =================
def update_github_readme(repo_full_name):
    log(f"✏️ 准备更新 {repo_full_name} README")
    url = f"https://api.github.com/repos/{repo_full_name}/contents/README.md"
    headers = {"Authorization": f"Bearer {GH_TOKEN}"}

    # 获取当前 README 的 sha
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    sha = r.json()["sha"]
    log(f"🔑 获取到 README sha: {sha}")

    # 构造新的内容
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    new_content = f"offline\n\n修改时间: {timestamp}"
    encoded_content = base64.b64encode(new_content.encode()).decode()

    # 提交更新
    payload = {
        "message": f"标记 {repo_full_name} 为 offline",
        "content": encoded_content,
        "sha": sha
    }
    log(f"🚀 提交更新到 GitHub")
    r2 = requests.put(url, headers=headers, json=payload)
    r2.raise_for_status()
    log(f"✅ {repo_full_name} README 更新完成")

# ================= 主程序 =================
def main():
    log("🟢 脚本开始执行")
    session = create_session()

    # 获取服务器列表
    try:
        servers = fetch_servers(session)
    except PermissionError:
        log("⚠️ 需要登录")
        login(session)
        servers = fetch_servers(session)

    now = int(datetime.now().timestamp())
    log("🕒 开始遍历服务器检查离线状态")

    for s in servers:
        name = s.get("name", "unknown")
        last_active = s.get("last_active", 0)

        # 转换 last_active 为时间戳
        try:
            last_ts = int(last_active)
        except:
            try:
                last_ts = int(datetime.fromisoformat(last_active.replace("Z","+00:00")).timestamp())
            except:
                last_ts = 0

        log(f"🔍 检查 {name}, last_active={last_ts}")

        # 离线判断
        if now - last_ts > 600:  # 离线阈值 10 分钟
            log(f"⚠️ {name} 离线")
            if name in SERVER_TO_REPO:
                update_github_readme(SERVER_TO_REPO[name])
            else:
                log(f"ℹ️ {name} 不在需更新的列表中")
        else:
            log(f"✅ {name} 在线")

    log("🎉 脚本执行完毕")

if __name__ == "__main__":
    main()
