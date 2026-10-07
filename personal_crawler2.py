"""用已保存的登录 cookies 抓取教务系统个人信息页面（不启动浏览器）。

方案：从 portal_state.json 提取 cookies，用 requests 直接发 HTTP 请求。
优势：不需要启动 Chromium，避免 GPU/内存冲突。
前置：portal_state.json 存在（由 login_window.py 生成）

用法: python personal_crawler2.py [--pages xj,cj,xkxf]
"""
import os
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = os.environ.get("JW_BASE", "http://jw.example.edu.cn")
STATE_FILE = Path(__file__).parent / "portal_state.json"
OUT = Path(__file__).parent / "personal_data.json"

PAGES = {
    "xj":      ("学籍信息",     "student/xj.php"),
    "zc":      ("注册信息",     "student/zc.php"),
    "cj":      ("成绩考核",     "student/chengji.php"),
    "cjp":     ("成绩与排名",   "student/chengjiPm.php"),
    "xkxf":    ("选课学分统计", "student/xkxfTj.php"),
    "kb":      ("课表查询",     "student/kebiao.php"),
    "ksap":    ("考试安排",     "student/ksap.php"),
    "byxf":    ("毕业学分学费", "student/byxfjs.php"),
    "skjh":    ("授课计划",     "student/skjh.php"),
    "jiaocai": ("教材信息",     "student/jiaocai.php"),
}

# 个人信息主页（用于提取基础信息 + 确认登录态）
HOME_URL = f"{BASE}/user.php"


def load_cookies() -> dict:
    """从 state 文件提取 cookies，过滤出有效的（未过期的）。"""
    if not STATE_FILE.exists():
        print(f"[错误] 未找到 {STATE_FILE}")
        print("       请先运行: python login_window.py")
        return {}

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    cookies = {}
    now = datetime.now().timestamp()

    for c in state.get("cookies", []):
        # 过滤已过期 cookie
        exp = c.get("expires", -1)
        if exp > 0 and exp < now:
            continue
        # session cookie (expires=-1) 保留
        cookies[c["name"]] = c["value"]

    return cookies


def clean_html(html: str) -> str:
    """HTML → 可读纯文本，保留表格结构。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "iframe", "noscript"]):
        tag.decompose()
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if cells:
            tr.replace_with(" | ".join(cells))
    text = soup.get_text("\n", strip=True)
    return "\n".join(l for l in text.split("\n") if l.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="xj,zc,cj,cjp,xkxf,kb,ksap,byxf",
                    help="逗号分隔的页面 key")
    ap.add_argument("--home", action="store_true", help="只抓 user.php 首页")
    a = ap.parse_args()

    cookies = load_cookies()
    if not cookies:
        return

    print(f"加载 {len(cookies)} 个 cookies")

    # 创建 session
    s = requests.Session()
    s.cookies.update(cookies)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": HOME_URL,
    })

    # 1) 先访问首页确认登录态
    print(f"\n[1/2] 确认登录态: {HOME_URL}")
    try:
        r = s.get(HOME_URL, timeout=15)
        print(f"  状态: {r.status_code}, 长度: {len(r.text)}")
        text = clean_html(r.text)
        if "学号" not in text and "注销" not in text:
            print(f"  [警告] 未检测到登录信息，可能 cookie 无效")
        else:
            print(f"  [OK] 登录态有效")
    except Exception as e:
        print(f"  [失败] {str(e)[:80]}")
        return

    # 抓首页基础信息
    home_text = clean_html(s.get(HOME_URL, timeout=15).text)

    if a.home:
        print(f"\n=== 首页文本 ===\n{home_text[:1500]}")
        return

    # 2) 抓各个人信息页面
    keys = [k.strip() for k in a.pages.split(",") if k.strip()]
    result = {"home": {"name": "个人信息主页", "url": HOME_URL,
                       "text": home_text, "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M")}}

    print(f"\n[2/2] 抓取 {len(keys)} 个个人页面")
    for i, key in enumerate(keys, 1):
        if key not in PAGES:
            print(f"  [{i}/{len(keys)}] 未知 key '{key}'，跳过")
            continue
        name, path = PAGES[key]
        url = f"{BASE}/{path}"
        print(f"  [{i}/{len(keys)}] {name} ({path})", end="... ")
        try:
            r = s.get(url, timeout=15)
            if r.status_code == 412:
                print("412 WAF")
                continue
            text = clean_html(r.text)
            # 判断是否跳回登录
            if "统一身份认证" in text[:500] or len(text) < 50:
                print(f"登录失效或空内容({len(text)}字)")
                continue
            result[key] = {
                "name": name,
                "title": re.search(r"<title>([^<]+)</title>", r.text).group(1)
                         if re.search(r"<title>([^<]+)</title>", r.text) else "",
                "url": url,
                "text": text,
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            print(f"OK {len(text)}字")
        except Exception as e:
            print(f"失败: {str(e)[:50]}")

    if result:
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n完成：{len(result) - 1}/{len(keys)} 个页面 → {OUT.name}")


if __name__ == "__main__":
    main()
