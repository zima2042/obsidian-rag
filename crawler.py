"""教务系统（Portal）爬取器：Playwright 绕过瑞数 WAF，抓通知公告（近 N 个月）并去重。

用法:
  python crawler.py --dump                     # 调试：dump 列表页 HTML
  python crawler.py --list-only --months 6     # 只抓列表不抓正文
  python crawler.py --limit 80 --months 6      # 抓近 6 个月公告正文

原理:
  瑞数 WAF ($_ts) 会识别 headless=True 直接返回 412。
  解法: headless=False + --disable-blink-features=AutomationControlled,
        先访问首页让 $_ts JS 执行生成 Cookie, 再访问子页面。
  分页: VSBuilder CMS, tzgg.htm → tzgg/118.htm, 页码倒序 (尾页号=总页数)。
        如 '1/118' 表示共 118 页, 第 n 页 = tzgg/(118-n+1).htm。
输出:
  crawled_data.json  按 url 去重的 {title,url,date,markdown,fetched_at}
"""
import os
import argparse
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = os.environ.get("JW_BASE", "http://jw.example.edu.cn")
OUT = Path(__file__).parent / "crawled_data.json"

# 栏目配置: key -> (名称, 列表页路径)
SECTIONS = {
    "tzgg": ("通知公告", "tzgg.htm"),
    "jxgg": ("教学公告", "jxgg.htm"),
    "ksa":  ("考试工作", "ks.htm"),
}

_waf_warmed = False


# ---------- WAF ----------

def warm_up_waf(page) -> None:
    """访问首页, 执行 $_ts 混淆 JS 生成瑞数 Cookie (按域名共享)。"""
    global _waf_warmed
    if _waf_warmed:
        return
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(3500)  # 等 $_ts 完成并写 Cookie
    _waf_warmed = True


def fetch_page(page, url: str, retries: int = 3) -> str:
    """Playwright 取 HTML。遇 412/空 → 重新暖机重试。"""
    warm_up_waf(page)
    last = ""
    for i in range(retries + 1):
        try:
            r = page.goto(url, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(2500)
            status = r.status if r else 0
            html = ""
            for _ in range(3):  # 页面可能仍在导航, 重试取 content
                try:
                    html = page.content()
                    break
                except Exception:
                    page.wait_for_timeout(1200)
            if status == 412:
                print(f"    412 WAF 拦截 -> 重新暖机 ({i+1}/{retries})")
                warm_up_waf(page)
            else:
                last = html
                if status in (200, 301, 302) and len(html) > 2000:
                    return html
        except Exception as e:
            print(f"    重试 {i+1}: {str(e)[:70]}")
            page.wait_for_timeout(3000)
            warm_up_waf(page)
    return last


# ---------- 列表解析 ----------

def parse_list(html: str) -> list[dict]:
    """从列表页提取 标题/链接/日期。"""
    soup = BeautifulSoup(html, "lxml")
    items = []
    anchors = [a for a in soup.find_all("a", href=re.compile(r"info/\d+/\d+"))]
    for a in anchors:
        title = a.get_text(strip=True)
        # 标题末尾常粘着日期 ("xxx通知2026-08-28"), 剥掉
        title = re.sub(r"\s*\d{4}-\d{1,2}-\d{1,2}$", "", title).strip()
        href = a.get("href", "")
        if not title or len(title) < 4:
            continue
        date = ""
        parent = a.find_parent(["li", "tr", "div"])
        if parent:
            m = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})",
                          parent.get_text(" ", strip=True))
            if m:
                date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        if href.startswith("http"):
            full = href
        elif href.startswith("/"):
            full = BASE + href
        else:
            full = f"{BASE}/{href}"
        items.append({"title": title, "url": full, "date": date})
    # 按 url 去重
    seen, uniq = set(), []
    for it in items:
        if it["url"] not in seen:
            seen.add(it["url"])
            uniq.append(it)
    return uniq


def total_pages(html: str) -> int:
    """从分页块读总页数, 如 '1/118' -> 118。"""
    m = re.search(r"(\d+)/(\d+)</span>", html)
    return int(m.group(2)) if m else 1


def page_url_for(section_path: str, n: int, total: int) -> str:
    """第 n 页 URL。尾页号=total, 页码从 total 递减到 1。"""
    if n == 1:
        return f"{BASE}/{section_path}"
    return f"{BASE}/{section_path.replace('.htm','')}/{total - n + 1}.htm"


# ---------- 正文 ----------

def html_to_markdown(html: str, title: str = "") -> str:
    """通知正文 HTML -> 简洁 Markdown。"""
    soup = BeautifulSoup(html, "lxml")
    box = soup.select_one("#vsb_content, .v_news_content, #vsb_content_info, .content, article")
    scope = box or soup.find("body") or soup
    for tag in scope.find_all(["script", "style", "iframe", "img", "input", "nav", "header", "footer"]):
        tag.decompose()
    lines = []
    if title:
        lines += [f"# {title}", ""]
    for el in scope.find_all(["h1", "h2", "h3", "p", "div", "tr", "li", "br"]):
        if el.name in ("div", "tr") and len(el.get_text(strip=True)) > 200:
            continue  # 跳过容器性大段
        text = el.get_text(" ", strip=True)
        if text and text not in lines[-1:]:
            lines.append(text)
    md = "\n\n".join(l for l in lines if l.strip())
    return md if md.strip() else scope.get_text(" ", strip=True)[:2000]


# ---------- 持久化 ----------

def load_existing() -> dict:
    """读历史数据, 按 url 建索引 (每天定时跑时避免重复抓)。"""
    if OUT.exists():
        try:
            return {it["url"]: it for it in json.loads(OUT.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return {}


def save_existing(data: dict) -> None:
    OUT.write_text(json.dumps(list(data.values()), ensure_ascii=False, indent=2),
                   encoding="utf-8")


# ---------- 主流程 ----------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--section", default="tzgg")
    p.add_argument("--limit", type=int, default=80, help="本次最多抓正文条数")
    p.add_argument("--months", type=int, default=6, help="只保留近 N 个月公告")
    p.add_argument("--max-pages", type=int, default=30, help="最多翻多少页")
    p.add_argument("--dump", action="store_true")
    p.add_argument("--list-only", action="store_true")
    a = p.parse_args()

    if a.section not in SECTIONS:
        print(f"未知栏目 {a.section}, 可选: {list(SECTIONS)}")
        return

    name, path = SECTIONS[a.section]
    list_url = f"{BASE}/{path}"
    cutoff = datetime.now() - timedelta(days=30 * a.months)
    existing = load_existing()
    fresh = 0

    with sync_playwright() as pw:
        # headless=False + 关闭自动化特征: 瑞数 WAF 会识别 headless=True 直接 412
        browser = pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page()

        if a.dump:
            html = fetch_page(page, list_url)
            Path("debug_list.html").write_text(html, encoding="utf-8")
            print(f"HTML 已存 debug_list.html ({len(html)} 字符)")
            print(f"总页数: {total_pages(html)}")
            print(f"解析到: {len(parse_list(html))} 条")
            browser.close()
            return

        # [1/3] 列表 + 翻页
        print(f"[1/3] 抓列表: {name} ({list_url})")
        html = fetch_page(page, list_url)
        items = parse_list(html)
        total = total_pages(html)
        print(f"      第1页 {len(items)} 条, 总页数 {total}, 时间窗 {a.months} 个月")

        pn = 1
        while pn < total and pn < a.max_pages:
            url = page_url_for(path, pn + 1, total)
            h = fetch_page(page, url)
            page_items = parse_list(h)
            if not page_items:
                print(f"      第 {pn+1} 页无结果, 停止翻页")
                break
            items += page_items
            oldest = next((it["date"] for it in page_items if it["date"]), "")
            print(f"      第 {pn+1} 页 +{len(page_items)} 条 (该页最早 {oldest})")
            if oldest:
                try:
                    if datetime.strptime(oldest, "%Y-%m-%d") < cutoff:
                        print(f"      已超出时间窗, 停止翻页")
                        break
                except ValueError:
                    pass
            pn += 1

        # 过滤: 时间窗内 + 未抓过正文 + 跨页去重
        # 注意: 不删除超出时间窗的旧条目 (load_existing 已保留全部历史),
        # 只跳过时间窗外 + 已有正文的, 实现 "每天只新增, 不删除" 的增量更新。
        seen, todo = set(), []
        for it in items:
            if it["url"] in seen:
                continue
            if it["url"] in existing and existing[it["url"]].get("markdown"):
                continue  # 已抓过正文, 跳过 (不重复抓, 不删除)
            if it["date"]:
                try:
                    if datetime.strptime(it["date"], "%Y-%m-%d") < cutoff:
                        continue  # 超时间窗, 本轮不抓 (但已抓的旧数据仍保留)
                except ValueError:
                    pass
            seen.add(it["url"])
            todo.append(it)

        # [2/3] 正文
        print(f"[2/3] 待抓正文 {len(todo)} 条 (上限 {a.limit})")
        if not a.list_only:
            for i, it in enumerate(todo[:a.limit]):
                try:
                    md = html_to_markdown(fetch_page(page, it["url"]), it["title"])
                    it["markdown"] = md
                    fresh += 1
                    print(f"      [{i+1}/{min(len(todo),a.limit)}] {it['title'][:34]} -> {len(md)} 字")
                    time.sleep(0.6)  # 礼貌延迟, 避免风控
                except Exception as e:
                    print(f"      [{i+1}] 失败: {str(e)[:60]}")
                    it["markdown"] = ""
        browser.close()

        # [3/3] 持久化
        print("[3/3] 写入 crawled_data.json")
        for it in todo[:a.limit]:
            it["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            existing[it["url"]] = it
        save_existing(existing)
        print(f"完成: 新增正文 {fresh} 条, 库内共 {len(existing)} 条")


if __name__ == "__main__":
    main()
