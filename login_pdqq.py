"""登录腾讯频道网页版 pd.qq.com，保存登录态用于后续抓取。v2

改进：自动点击【登录】按钮弹出二维码；更可靠地检测登录成功
（页面出现"退出登录/个人中心/我的频道"导航，或 URL 变化）。

用法: python login_pdqq.py
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_FILE = Path(__file__).parent / "pdqq_state.json"


def main():
    print("=" * 56)
    print("  腾讯频道网页版登录助手 v2")
    print("=" * 56)
    print("  1) 浏览器窗口将弹出 pd.qq.com")
    print("  2) 我会自动点击【登录】弹出二维码")
    print("  3) 请用手机 QQ 扫描二维码登录小号")
    print("  4) 登录成功后自动保存状态")
    print("=" * 56)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            timeout=60000,
        )
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = ctx.new_page()

        page.goto("https://pd.qq.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        print(f"\n[当前URL] {page.url}")

        # 尝试自动点击登录按钮
        try:
            clicked = page.evaluate("""() => {
                const candidates = [
                    'text=登录',
                    'button:has-text("登录")',
                    '.login-btn, .header-login, [class*="login"]'
                ];
                for (const sel of candidates) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const t = (el.innerText || '').trim();
                        if (t === '登录' || t.includes('登录')) {
                            el.click();
                            return sel;
                        }
                    }
                }
                return null;
            }""")
            print(f"[自动点击登录] {'成功: '+clicked if clicked else '未找到按钮，请手动点击右上角【登录】'}")
        except Exception as e:
            print(f"[自动点击登录] 异常: {e}，请手动点击")

        page.wait_for_timeout(3000)

        print("\n>>> 请用手机QQ扫描浏览器里弹出的二维码，等待 180 秒...")
        logged_in = False
        for i in range(180):
            time.sleep(1)
            try:
                body_text = page.evaluate("() => document.body ? document.body.innerText.slice(0, 4000) : ''")
                url = page.url
                # 可靠标志：出现"退出登录"或"我的频道"导航 + 不再显示"登录"按钮
                has_logout = "退出登录" in body_text or "个人中心" in body_text
                has_my_channel = "我的频道" in body_text or "我的动态" in body_text
                # 登录按钮消失（说明已登录）
                login_btn_gone = "登录" not in body_text.split("\n")[:6]
                if has_logout or (has_my_channel and login_btn_gone):
                    print(f">>> 检测到登录成功！第 {i+1} 秒")
                    logged_in = True
                    break
            except Exception:
                pass

        if not logged_in:
            print(">>> 未检测到明确登录标志，仍保存当前浏览器状态（如已登录则有效）")

        ctx.storage_state(path=str(STATE_FILE))
        print(f"\n[状态已保存] {STATE_FILE}")
        print(f"[页面标题] {page.title()}")

        time.sleep(8)
        browser.close()
        print("DONE")


if __name__ == "__main__":
    main()