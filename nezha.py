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
NEZHA_JWT  = os.getenv("NEZHA_JWT")

README_FILE = "README.md"
DATA_FILE   = Path("nezha_latency.json")

TZ = ZoneInfo("Asia/Shanghai")
OFFLINE_SECONDS = 60

START = "<!-- NEZHA-LATENCY-START -->"
END   = "<!-- NEZHA-LATENCY-END -->"

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
    log("🔐 Cookie 失效，开始登录")

    r = session.post(
        f"{NEZHA_URL}/api/v1/login",
        json={"username": NEZHA_USER, "password": NEZHA_PASS},
        timeout=10
    )

    log(f"登录 HTTP 状态码: {r.status_code}")
    r.raise_for_status()

    if "nz-jwt" not in session.cookies.get_dict():
        raise RuntimeError("❌ 登录失败，未获取 nz-jwt")

    log("✅ 登录成功")

# ================= 获取服务器 =================

def fetch_servers(session):
    url = NEZHA_URL + API_SERVER
    log(f"📡 请求服务器接口: {url}")

    r = session.get(url, timeout=10)
    log(f"HTTP 状态码: {r.status_code}")

    if r.status_code in (401, 403):
        raise PermissionError("Cookie 失效")

    r.raise_for_status()

    try:
        j = r.json()
    except Exception:
        log("❌ 返回内容无法解析为 JSON")
        log(r.text[:300])
        raise

    # ===== 关键兼容逻辑 =====
    servers = None

    if isinstance(j, dict):
        if "data" in j and isinstance(j["data"], list):
            servers = j["data"]
        else:
            log(f"⚠️ JSON dict 但无 data 字段，keys={list(j.keys())}")
    elif isinstance(j, list):
        servers = j

    if servers is None:
        log("❌ 无法识别的 JSON 结构")
        log(json.dumps(j, ensure_ascii=False)[:500])
        raise RuntimeError("服务器数据结构不支持")

    log(f"✅ 成功解析服务器列表：{len(servers)} 台")
    return servers

# ================= 在线判断 =================

def is_online(last_active_str):
    last = datetime.fromisoformat(last_active_str)
    now = datetime.now(timezone.utc)
    diff = (now - last.astimezone(timezone.utc)).total_seconds()
    return diff <= OFFLINE_SECONDS

# ================= Ping =================

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

# ================= 记录数据 =================

def record_latency(results):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    data = {}
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text())

    data[now] = results

    while len(data) > 48:
        data.pop(next(iter(data)))

    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    log("📝 延迟数据已保存")

# ================= 曲线 =================

def generate_chart():
    if not DATA_FILE.exists():
        return "暂无数据"

    data = json.loads(DATA_FILE.read_text())
    servers = set(k for v in data.values() for k in v)

    lines = []
    for s in
