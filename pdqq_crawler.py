"""腾讯频道「频道名」爬虫 v2。

从 pd.qq.com 网页版抓取频道帖子（登录态 headless 浏览器）：
- 抓频道主页"全部"流 + 点击每个分区 tab 抓对应分区
- 滚动加载帖子列表
- 进入每个帖子详情提取：标题、作者、发布时间、正文、评论
- 图片消息：下载到本地并用 OCR 提取文字（保留文字信息）
- 增量：按帖子 URL 去重，已抓过的不再重复抓
- 只读操作，不点赞不评论不发帖

用法:
  python pdqq_crawler.py              # 全量（首次）
  python pdqq_crawler.py --limit 20   # 指定最大帖子数（测试用）

前置: pdqq_state.json 存在（由 login_pdqq.py 生成）
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("QQ_CHANNEL_URL", "https://pd.qq.com/g/your-channel-id")
STATE_FILE = Path(__file__).parent / "pdqq_state.json"
DATA_FILE = Path(__file__).parent / "crawled_pdqq.json"
IMG_DIR = Path(__file__).parent / "pdqq_images"
LOCK_FILE = Path(__file__).parent / "pdqq_crawler.lock"

# 进程互斥锁：防止多个爬虫并发写 crawled_pdqq.json / 抢登录态（2026-10-01 曾因
# 4 个残留实例并发把同步搞得看起来"卡死"，实际是互相踩踏）
def acquire_lock() -> object | None:
    try:
        import msvcrt  # Windows only，本机平台即 Windows
    except ImportError:
        return None  # 非 Windows 跳过锁（本脚本只在本机跑）
    try:
        fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o644)
        f = os.fdopen(fd, "r+")
        # msvcrt.locking 的 LK_NBLCK 是原子"非阻塞尝试加锁"，等价 Windows LockFile()
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        # 已有实例持锁 → 直接退出，不碰数据文件
        try:
            f.close()
        except Exception:
            pass
        print("[锁] 已有 pdqq_crawler 实例在运行，本实例退出（防止并发写坏数据）")
        sys.exit(0)
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f

# 分区 tab（在频道主页里）
SUB_TABS = [
    "全部", "防骗指南", "🐒 闲置｜跳蚤市场", "📖 学习｜资料分享",
    "😺 黑板｜失物招领", "🤬 吐槽｜曝光大厅", "🛰️ 招募 ｜部门纳新＆兼职",
    "拼车上下山", "💖 便签｜表白捞人", "🀄 组局｜麻将棋牌", "志愿服务",
    "🍻 拼桌｜一起喝酒", "📷 图库｜美景分享", "📣 转载｜校园通知", "租房和转租",
]


def load_all() -> list[dict]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_all(items: list[dict]):
    DATA_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def scroll_feed(page, max_scrolls=25, pause=1.0):
    """滚动列表到底，加载更多。"""
    for i in range(max_scrolls):
        before = page.evaluate("() => document.body.innerText.length")
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(int(pause * 1000))
        after = page.evaluate("() => document.body.innerText.length")
        if after <= before + 200:
            break
    return i + 1


def extract_posts(page) -> list[dict]:
    """提取当前页面所有帖子链接（带作者/时间/标题）。"""
    posts = page.evaluate("""(baseUrl) => {
        const out = [];
        document.querySelectorAll('a[href*="/post/B_"]').forEach(a => {
            const m = a.href.match(/post\\/(B_[A-Za-z0-9]+)/);
            if (!m) return;
            const raw = (a.innerText || '').trim();
            const lines = raw.split('\\n').map(s => s.trim()).filter(Boolean);
            // 格式: [作者, 时间, 标题..., 点赞, N, N]
            out.push({
                url: baseUrl + '/post/' + m[1],
                author: lines[0] || '',
                time_raw: lines[1] || '',
                title: lines[2] || (lines[0] || ''),
                raw: raw.slice(0, 200),
            });
        });
        const seen = new Set();
        return out.filter(x => { if (seen.has(x.url)) return false; seen.add(x.url); return true; });
    }""", BASE)
    for p in posts:
        p["author"] = clean_text(p["author"])
        p["time_raw"] = clean_text(p["time_raw"])
        p["title"] = clean_text(p["title"])
    return posts


def ocr_image(path: Path) -> str:
    """OCR 图片文字（RapidOCR onnxruntime，模型内置）。"""
    try:
        from rapidocr_onnxruntime import RapidOCR
        ocr = getattr(ocr_image, "_ocr", None)
        if ocr is None:
            ocr = RapidOCR()
            ocr_image._ocr = ocr
        result, _ = ocr(str(path))
        if not result:
            return ""
        return " ".join(item[1] for item in result if len(item) > 1 and item[1])
    except Exception as e:
        print(f"    [OCR] 失败: {str(e)[:80]}")
        return ""


def download_images(pg, img_urls: list[str]) -> list[dict]:
    """下载图片并 OCR。"""
    out = []
    IMG_DIR.mkdir(exist_ok=True)
    for i, url in enumerate(img_urls):
        if not url or url.startswith("data:"):
            continue
        try:
            resp = pg.request.get(url, timeout=20000)
            if resp.ok and resp.headers.get("content-type", "").startswith("image"):
                ext = "." + (resp.headers.get("content-type", "image/png").split("/")[-1] or "png")
                path = IMG_DIR / f"{int(time.time())}_{i}{ext}"
                path.write_bytes(resp.body())
                ocr_txt = ocr_image(path)
                out.append({"url": url[:120], "local": str(path.name), "ocr_text": ocr_txt})
        except Exception as e:
            print(f"    [图] 下载失败: {str(e)[:60]}")
    return out


def parse_post_detail(pg, post_url: str) -> dict | None:
    """打开帖子详情页，提取正文+图片+评论。"""
    try:
        pg.goto(post_url, wait_until="domcontentloaded", timeout=40000)
        pg.wait_for_timeout(3000)
        pg.mouse.wheel(0, 1200)
        pg.wait_for_timeout(1200)

        d = pg.evaluate("""() => {
            const t = document.body.innerText;
            const lines = t.split('\\n').map(s => s.trim()).filter(Boolean).filter(s => s.length < 1500);
            // 标题 = document.title 去掉频道后缀
            let title = document.title.replace(/｜.*/, '').trim();
            // 找"浏览 N" 定位正文起始
            let body = '';
            let bi = -1;
            for (let i=0; i<lines.length; i++) {
                if (/浏览\\d+|浏览 \\d+/.test(lines[i])) { bi = i; break; }
                if (/评论\\d+/.test(lines[i]) && i > 5) { bi = i; break; }
            }
            if (bi >= 0) {
                // 正文=浏览行后面的非互动文本，最多取 20 行
                const parts = [];
                for (let j=bi+1; j<Math.min(bi+25, lines.length); j++) {
                    const L = lines[j];
                    if (L === '点赞' || L === '回复' || L === '分享' || /^\\d+$/.test(L) || L === '热门' || L === '暂无更多评论' || L.startsWith('发言要友善') || L === '手机扫码分享') continue;
                    if (j > bi+1 && (L === '点赞' || L === '最新')) break;
                    parts.push(L);
                    if (parts.length > 15) break;
                }
                body = parts.join(' ');
            }
            // 图片
            const imgs = [...document.querySelectorAll('img')]
                .map(i => i.src || i.currentSrc)
                .filter(s => s && s.startsWith('http') && !s.includes('avatar') && !s.includes('emoji') && !s.includes('logo'));
            return {title, body, images: imgs.slice(0, 10)};
        }""")

        imgs = d.get("images") or []
        img_info = download_images(pg, imgs) if imgs else []
        return {
            "url": post_url,
            "title": clean_text(d.get("title", "")),
            "body": clean_text(d.get("body", "")),
            "images": img_info,
            "images_text": " ".join(x["ocr_text"] for x in img_info if x.get("ocr_text")),
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        print(f"    [详情] 失败: {str(e)[:80]}")
        return None


def crawl_sub(page, sub_name: str, items: list, known: set, limit: int) -> int:
    """抓取一个分区（或全部）。返回新增数。"""
    new_count = 0
    posts = extract_posts(page)
    print(f"  列表 {len(posts)} 条")
    for post in posts[:limit]:
        url = post["url"]
        if url in known:
            continue
        print(f"  ▶ [{post['title'][:22]}] ({post['time_raw']})", end=" ")
        detail = parse_post_detail(page, url)
        if detail and (detail["body"] or detail["images_text"]):
            detail.update({
                "sub": sub_name,
                "author": post["author"],
                "time_raw": post["time_raw"],
            })
            items.append(detail)
            known.add(url)
            new_count += 1
            print(f"✓ 文{len(detail['body'])}字 图{len(detail['images'])}")
            save_all(items)
        else:
            print("跳过(空)")
        time.sleep(0.6)
    return new_count


def main():
    lock_fh = acquire_lock()
    if lock_fh:
        print(f"[锁] 本实例持锁 (PID {os.getpid()})")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=150, help="每个分区最多抓 N 个帖子")
    ap.add_argument("--subs", default="", help="逗号分隔的分区名子串，空=全部")
    a = ap.parse_args()

    items = load_all()
    known = {x["url"] for x in items}
    print(f"已有 {len(items)} 条，去重后剩 {len(known)} 个 URL 待跳过")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-proxy-server"],
            timeout=60000,
        )
        ctx = browser.new_context(storage_state=str(STATE_FILE), viewport={"width": 1440, "height": 900}, locale="zh-CN")
        pg = ctx.new_page()

        # 打开频道主页（全部流）
        pg.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=40000)
        pg.wait_for_timeout(4000)

        total_new = 0

        # 1) 先抓"全部"
        sub_filter = a.subs
        if not sub_filter or "全部" in sub_filter:
            print("\n=== 分区: 全部 ===")
            # 切"最新"排序
            try:
                pg.evaluate("""() => { const el=[...document.querySelectorAll('div,span')].find(e=>(e.innerText||'').trim()==='最新'); if(el) el.click(); }""")
                pg.wait_for_timeout(1200)
            except Exception:
                pass
            scroll_feed(pg, max_scrolls=30)
            total_new += crawl_sub(pg, "全部", items, known, a.limit)

        # 2) 逐个点击分区 tab
        for tab in SUB_TABS:
            if tab == "全部":
                continue
            if sub_filter and not any(s in tab for s in sub_filter.split(",")):
                continue
            print(f"\n=== 分区: {tab} ===")
            try:
                # 回到主页，点击 tab
                pg.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=40000)
                pg.wait_for_timeout(2500)
                clicked = pg.evaluate("""(tab) => {
                    const els = [...document.querySelectorAll('div,span')];
                    const el = els.find(e => (e.innerText||'').trim() === tab);
                    if (el) { el.click(); return true; }
                    return false;
                }""", tab)
                pg.wait_for_timeout(2500)
                if not clicked:
                    print("  [点击失败]")
                    continue
                scroll_feed(pg, max_scrolls=25)
                total_new += crawl_sub(pg, tab, items, known, a.limit)
            except Exception as e:
                print(f"  [分区异常] {str(e)[:80]}")

        browser.close()

    if lock_fh:
        lock_fh.close()  # 释放文件锁，进程退出时 msvcrt 自动解锁

    print(f"\n完成！新增 {total_new} 条，总记录 {len(items)} 条")
    save_all(items)


if __name__ == "__main__":
    main()