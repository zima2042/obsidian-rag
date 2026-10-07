"""探测腾讯频道（QQ频道）网页版入口。"""
import requests

ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}

urls = [
    ("腾讯频道后端", "https://qun.qq.com/guild/"),
    ("腾讯频道 web", "https://qun.qq.com/channels"),
    ("频道小程序web", "https://channel.qq.com/"),
    ("QQ频道旧web", "https://qun.qq.com/guild/pc/"),
    ("频道API测试", "https://qun.qq.com/cgi-bin/guild/index"),
]

for name, url in urls:
    try:
        r = requests.get(url, headers=ua, timeout=8, allow_redirects=True)
        final = r.url
        print(f"[{name}] {url}\n   -> {r.status_code} {final[:90]}")
    except Exception as e:
        print(f"[{name}] {url}\n   -> 异常: {str(e)[:60]}")
    print()