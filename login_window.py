"""弹出浏览器窗口供手动登录教务系统，保存登录状态到 portal_state2.json。

用法: python login_window.py
流程: 弹出 Chromium → 你登录 → 检测登录后自动保存状态 → 关闭
"""
import os
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

CTX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pw_jw_profile")
STATE_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jw_state2.json")
_BASE = os.environ.get("JW_BASE", "http://jw.example.edu.cn").rstrip("/")
LOGIN_URL = os.environ.get("JW_LOGIN_URL") or (_BASE + "/tysfrz/navication.php?id=user")
_HOST = urlparse(LOGIN_URL).hostname or "jw.example.edu.cn"

os.makedirs(CTX_DIR, exist_ok=True)
print("LOGIN_WINDOW_READY")
print(">>> 浏览器已弹出，请登录教务系统")
print(f">>> 地址: {LOGIN_URL}")
print(">>> 登录成功后页面会显示『个人服务』，自动保存后关闭")
print(">>> 等待 180 秒")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        CTX_DIR,
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--no-zygote"],
        viewport={"width": 1280, "height": 900},
        ignore_https_errors=True,
    )
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        pg.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=40000)
    except Exception as e:
        print(f">>> 初始跳转异常（可忽略）: {str(e)[:60]}")

    ok = False
    for i in range(180):
        time.sleep(1)
        try:
            u = pg.url
            if _HOST in u and "ids." not in u:
                ok = True
                print(f">>> 登录成功！第 {i + 1} 秒, URL={u}")
                pg.wait_for_timeout(3000)
                break
        except Exception:
            print(f">>> 页面异常退出，第 {i + 1} 秒")
            break

    if ok:
        ctx.storage_state(path=STATE_OUT)
        print("STATE_SAVED")
    else:
        print("NO_LOGIN")
    ctx.close()
    print("DONE")
