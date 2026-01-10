#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nezha Monitor v1.14.12
- 使用环境变量登录哪吒面板
- 获取服务器状态
- 生成 README.md 状态表
"""

import os
import sys
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ===================== 环境变量 =====================

BASE_URL = os.getenv("NEZHA_URL")
USERNAME = os.getenv("NEZHA_USERNAME")
PASSWORD = os.getenv("NEZHA_PASSWORD")

TIMEOUT = 10
README_PATH = "README.md"

# ===================== 基础校验 =====================

if not BASE_URL or not USERNAME or not PASSWORD:
    print("❌ 缺少必要环境变量：")
    print("NEZHA_URL / NEZHA_USERNAME / NEZHA_PASSWORD")
    sys.exit(1)

BASE_URL = BASE_URL.rstrip("/")

# ===================== 日志 =====================

def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

# ===================== 登录 =====================

def login_and_get_session():
    url = f"{BASE_URL}/api/v1/login"

    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "nezha-client/1.14.12",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/dashboard/login",
    }

    payload = {
        "username": USERNAME,
        "password": PASSWORD
    }

    sess = requests.Session()

    log("🔐 正在登录哪吒面板")
    resp = sess.post(url, json=payload, headers=headers, timeout=TIMEOUT)

    log(f"HTTP 状态码: {resp.status_code}")

    if resp.status_code != 200:
        log("❌ 登录失败")
        sys.exit(1)

    cookies = sess.cookies.get_dict()
    log(f"cookies：{cookies}")
    if "nz-jwt" not in cookies:
        log("❌ 未获取到 nz_session（账号或密码错误？）")
        sys.exit(1)

    nz_session = cookies["nz_session"]
    log(f"✅ 登录成功，Session: {nz_session[:6]}***{nz_session[-6:]}")

    return sess

# ===================== 获取服务器 =====================

def get_servers(sess):
    url = f"{BASE_URL}/api/v1/server"

    log("📡 请求服务器列表 API")
    resp = sess.get(url, timeout=TIMEOUT)

    log(f"HTTP 状态码: {resp.status_code}")

    if resp.status_code != 200:
        log("❌ API 请求失败，Session 可能失效")
        sys.exit(1)

    data = resp.json()
    if "data" not in data:
        log("❌ 返回数据结构异常")
        sys.exit(1)

    return data["data"]

# ===================== README 表格 =====================

def generate_readme_table(servers):
    rows = []
    for s in servers:
        online = s.get("online", True)
        status = "✅ 在线" if online else "🚨 离线"
        name = s.get("name", "-")
        ip = s.get("ip", "-")
        last = s.get("last_active", "-")
        rows.append(f"| {status} | {name} | {ip} | {last} |")

    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")

    table = [
        "## 📊 哪吒服务器状态",
        "",
        "| 状态 | 名称 | IP | 最后活跃 |",
        "|----|----|----|----|",
        *rows,
        "",
        f"_更新时间：{now}（北京时间）_",
    ]

    return "\n".join(table)

def update_readme(table_md):
    start = "<!-- NEZHA-STATUS-START -->"
    end = "<!-- NEZHA-STATUS-END -->"

    if not os.path.exists(README_PATH):
        log("❌ README.md 不存在")
        sys.exit(1)

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if start not in content or end not in content:
        log("❌ README 中缺少 NEZHA 标记区块")
        sys.exit(1)

    new_block = f"{start}\n{table_md}\n{end}"

    before = content.split(start)[0]
    after = content.split(end)[1]

    new_content = before + new_block + after

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

# ===================== 主流程 =====================

def main():
    log("🚀 哪吒 README 状态任务启动")

    sess = login_and_get_session()
    servers = get_servers(sess)

    log(f"📊 服务器总数: {len(servers)}")

    offline = [s for s in servers if not s.get("online", True)]
    log(f"🚨 离线服务器数量: {len(offline)}")

    log("🧾 生成 README 状态表")
    table_md = generate_readme_table(servers)

    update_readme(table_md)
    log("✅ README.md 已更新完成")

if __name__ == "__main__":
    main()
