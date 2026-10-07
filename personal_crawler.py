"""个人信息爬虫：用已保存的登录态抓取教务系统个人数据页面。

前置：先运行 login_window.py 弹出浏览器登录，保存 portal_state.json
用法: python personal_crawler.py [--pages xj,cj,xkxf,kb] [--dump]

抓取的个人数据页（均为登录后可见的个人页面）：
  xj     学籍信息   student/xj.php
  zc     注册信息   student/zc.php
  cj     成绩考核   student/chengji.php
  cjp    成绩与排名 student/chengjiPm.php
  xkxf   学分统计   student/xkxfTj.php
  kb     课表查询   student/kebiao.php
  ksap   考试安排   student/ksap.php
  byxf   毕业学分   student/byxfjs.php
输出：personal_data.json {page_key: {title, url, text, html, fetched_at}}
"""
import os
import argparse
import json
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = os.environ.get("JW_BASE", "http://jw.example.edu.cn")
STATE = Path(__file__).parent / "portal_state.json"
OUT = Path(__file__).parent / "personal_data.json"

PAGES = {
    "xj":   ("学籍信息", "student/xj.php"),
    "zc":   ("注册信息", "student/zc.php"),
    "cj":   ("成绩考核", "student/chengji.php"),
    "cjp":  ("成绩与排名", "student/chengjiPm.php"),
    "xkxf": ("选课学分统计", "student/xkxfTj.php"),
    "kb":   ("课表查询", "student/kebiao.php"),
    "ksap": ("考试安排", "student/ksap.php"),
    "byxf": ("毕业学分学费", "student/byxfjs.php"),
    "skjh": ("授课计划", "student/skjh.php"),
    "jiaocai": ("教材信息", "student/jiaocai.php"),
}


def clean_text(html: str) -> str:
    """HTML → 可读纯文本（保留表格结构，按行输出）。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "iframe", "noscript"]):
        tag.decompose()
    # 表格行加分隔符，便于阅读
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if cells:
            tr.replace_with(" | ".join(cells))
    text = soup.get_text("\n", strip=True)
    return "\n".join(line for line in text.split("\n") if line.strip())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="xj,zc,cj,cjp,xkxf,kb,ksap,byxf",
                    help="逗号分隔的页面 key")
    ap.add_argument("--dump", action="store_true", help="只抓首页 user.php")
    a = ap.parse_args()

    if not STATE.exists():
        print(f"[错误] 未找到登录状态 {STATE}")
        print("       请先运行 login_window.py 弹出浏览器登录教务系统")
        return

    keys = [k.strip() for k in a.pages.split(",") if k.strip()]
    result = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False,
                                     args=["--disable-blink-features=AutomationControlled",
                                           "--no-zygote"])
        ctx = browser.new_context()
        # 用 add_cookies 注入登录态（不依赖持久化 profile 目录，避免锁冲突）
        ctx.add_cookies(json.loads(STATE.read_text(encoding="utf-8"))["cookies"])
        page = ctx.new_page()

        # 先暖机个人主页，确认登录态有效
        print("[0/10] 确认登录态...")
        page.goto(f"{BASE}/user.php", wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(3000)
        if "logout.php" not in page.content() and "注销" not in page.content():
            print("  [错误] 登录态已失效，请重新运行 login_window.py 登录")
            browser.close()
            return
        print("  登录态有效")

        if a.dump:
            soup = BeautifulSoup(page.content(), "lxml")
            print(soup.get_text(" ", strip=True)[:1000])
            browser.close()
            return

        total = len(keys)
        for i, key in enumerate(keys, 1):
            if key not in PAGES:
                print(f"[{i}/{total}] 未知 key {key}, 跳过")
                continue
            name, path = PAGES[key]
            url = f"{BASE}/{path}"
            print(f"[{i}/{total}] {name} ({path})")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(2500)
                html = page.content()
                text = clean_text(html)
                # 判断是否跳回登录
                if page.url != url and "ids.example.edu.cn" in page.url:
                    print(f"    [警告] 跳转登录页，跳过")
                    continue
                result[key] = {
                    "name": name,
                    "title": page.title(),
                    "url": url,
                    "text": text,
                    "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
                print(f"    抓到 {len(text)} 字")
            except Exception as e:
                print(f"    [失败] {str(e)[:70]}")
            # 礼貌延迟，避免风控
            page.wait_for_timeout(1000)
        browser.close()

    if result:
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n完成：抓到 {len(result)}/{total} 个页面 → {OUT.name}")


if __name__ == "__main__":
    main()
