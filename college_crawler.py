"""学院官网爬虫。

从 ee.example.edu.cn 抓取通知公告和学院新闻，
模式模仿 crawler.py（教务在线）：
- Playwright headless=False 绕过 WAF
- 分页翻页抓取列表
- 进入详情页提取标题+正文
- 输出 crawled_college.json

用法:
  python college_crawler.py --section tzgg --pages 5   # 通知公告前5页
  python college_crawler.py --section xyxw --pages 3    # 学院新闻前3页
  python college_crawler.py --all                        # 全部栏目
"""
import os
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

BASE = os.environ.get("EE_BASE", "https://ee.example.edu.cn")
SECTIONS = {
    "tzgg": {"name": "通知公告", "url": f"{BASE}/index/tzgg.htm"},
    "xyxw": {"name": "学院新闻", "url": f"{BASE}/index/xyxw.htm"},
}
DATA_FILE = Path(__file__).parent / "crawled_college.json"


def load_all() -> list:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_all(items: list):
    DATA_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def get_next_page_url(page, current_url: str) -> str | None:
    """从分页导航找下一页 URL（VSBuilder CMS 风格：/index/tzgg/1.htm）。"""
    href = page.evaluate("""() => {
        const links = [...document.querySelectorAll('a')];
        const next = links.find(a => (a.innerText||'').trim() === '下页' || (a.title||'') === '下页');
        return next ? next.href : null;
    }""")
    return href


def extract_list(page) -> list[dict]:
    """从列表页提取帖子（标题+链接+日期）。"""
    items = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('a').forEach(a => {
            const t = (a.innerText||'').trim();
            const h = a.href||'';
            if (t && t.length > 6 && t.length < 120 && h.includes('/info/') && h.endsWith('.htm')) {
                out.push({title: t, url: h});
            }
        });
        const seen = new Set();
        return out.filter(x => { if(seen.has(x.url)) return false; seen.add(x.url); return true; });
    }""")
    return [{"title": clean_text(i["title"]), "url": i["url"]} for i in items]


def parse_detail(page, url: str) -> dict | None:
    """打开详情页提取标题+正文。"""
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2500)
        d = page.evaluate("""() => {
            const title = document.querySelector('h1, .title, .article-title, .news-title')?.innerText?.trim()
                || document.title.split('-')[0].trim();
            const body = document.querySelector('.v_news_content, .article, .content, #vsb_content, .news_content')?.innerText?.trim()
                || document.body.innerText.slice(0, 5000);
            const date = document.body.innerText.match(/20\\d{2}-\\d{2}-\\d{2}/)?.[0] || '';
            return {title, body, date};
        }""")
        return {
            "title": clean_text(d.get("title", "")),
            "body": clean_text(d.get("body", "")),
            "date": d.get("date", ""),
            "url": url,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        print(f"    [详情] 失败 {url}: {str(e)[:80]}")
        return None


def crawl_section(page, section_key: str, max_pages: int) -> list:
    """抓一个栏目（翻页）。"""
    sec = SECTIONS[section_key]
    print(f"\n=== {sec['name']} ===")
    items = []
    url = sec["url"]
    known = {x["url"] for x in load_all()}

    for pno in range(max_pages):
        print(f"  [页 {pno+1}] {url}")
        try:
            page.goto(url, wait_until="networkidle", timeout=40000)
            page.wait_for_timeout(4000)
            posts = extract_list(page)
            print(f"  列表 {len(posts)} 条")
            for post in posts:
                if post["url"] in known:
                    continue
                print(f"    ▶ [{post['title'][:30]}]", end=" ")
                detail = parse_detail(page, post["url"])
                if detail and detail["body"]:
                    detail["section"] = sec["name"]
                    items.append(detail)
                    known.add(post["url"])
                    print(f"✓ {len(detail['body'])}字")
                else:
                    print("跳过")
                time.sleep(0.5)
            # 翻下一页
            nxt = get_next_page_url(page, url)
            if not nxt or nxt == url:
                print("  无更多页")
                break
            url = nxt
        except Exception as e:
            print(f"  [页异常] {str(e)[:80]}")
            break

    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="tzgg", help="栏目：tzgg(通知公告) / xyxw(学院新闻)")
    ap.add_argument("--pages", type=int, default=5, help="最多翻 N 页")
    ap.add_argument("--all", action="store_true", help="抓所有栏目")
    a = ap.parse_args()

    all_items = load_all()
    known = {x["url"] for x in all_items}
    print(f"已有 {len(all_items)} 条")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-proxy-server"],
            timeout=60000,
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = ctx.new_page()

        if a.all:
            for key in SECTIONS:
                new = crawl_section(page, key, a.pages)
                all_items.extend(new)
                save_all(all_items)
        else:
            new = crawl_section(page, a.section, a.pages)
            all_items.extend(new)
            save_all(all_items)

        browser.close()

    print(f"\n完成！新增 {len(all_items) - len(known)} 条，总记录 {len(all_items)} 条")


if __name__ == "__main__":
    main()