"""把 QQ 频道抓取结果导入 Obsidian vault。

输入: crawled_pdqq.json（pdqq_crawler.py 生成）
输出: Obsidian Vault/QQ频道/频道名/<分区>/<日期>_<标题>.md

每帖一篇笔记，frontmatter 保留来源元数据（频道/分区/作者/时间/URL），
正文 = 标题 + 正文 + 图片OCR文字 + 评论。
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

from config import VAULT_PATH

FOLDER = "QQ频道"
CHANNEL = os.environ.get("QQ_CHANNEL_NAME", "频道名")
DATA_FILE = Path(__file__).parent / "crawled_pdqq.json"


def safe_filename(title: str) -> str:
    """清理 Windows 非法字符，长度截断。"""
    s = re.sub(r'[\\/:*?"<>|]', "-", title).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:50] or "未命名"


def build_md(it: dict) -> str:
    """生成笔记 Markdown 正文。"""
    lines = [f"# {it.get('title', '未命名')}", ""]
    lines.append(f"> 分区：{it.get('sub', '')}｜作者：{it.get('author', '')}｜发布于 {it.get('time_raw', '')}")
    lines.append("")

    body = it.get("body", "").strip()
    if body:
        lines.append(body)
        lines.append("")

    # 图片 OCR 文字
    img_text = it.get("images_text", "").strip()
    if img_text:
        lines.append("### 📷 图片文字（OCR）")
        lines.append(img_text)
        lines.append("")

    # 图片文件引用
    imgs = it.get("images") or []
    if imgs:
        lines.append("### 🖼️ 图片")
        for im in imgs:
            ocr_note = f"（OCR: {im['ocr_text'][:60]}）" if im.get("ocr_text") else ""
            lines.append(f"- `{im.get('local', '')}` {ocr_note}")
        lines.append("")

    lines.append("---")
    lines.append(f"来源：[帖子]({it.get('url', '')})｜抓取于 {it.get('fetched_at', '')}")
    return "\n".join(lines)


def main():
    if not DATA_FILE.exists():
        print("未找到 crawled_pdqq.json，请先运行 pdqq_crawler.py")
        return

    items = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    print(f"共 {len(items)} 条帖子")

    base = VAULT_PATH / FOLDER / CHANNEL
    count = 0
    skipped = 0
    for it in items:
        sub = (it.get("sub") or "未分区").strip() or "未分区"
        title = safe_filename(it.get("title", "未命名"))
        folder = base / sub
        folder.mkdir(parents=True, exist_ok=True)

        # 幂等：同名文件跳过
        fname = f"{title}.md"
        target = folder / fname
        if target.exists():
            skipped += 1
            continue

        md = build_md(it)
        # frontmatter
        meta = "\n".join([
            "---",
            f'title: "{it.get("title", "未命名")}"',
            f'source: "QQ频道:{CHANNEL}/{sub}"',
            f'url: "{it.get("url", "")}"',
            f'author: "{it.get("author", "")}"',
            f'sent_at: "{it.get("time_raw", "")}"',
            f'sub: "{sub}"',
            f'fetched_at: "{it.get("fetched_at", "")}"',
            'type: "QQ频道"',
            "---",
            "",
        ])
        target.write_text(meta + md, encoding="utf-8")
        count += 1

    print(f"导入完成：新增 {count} 篇，跳过 {skipped} 篇（已存在）")
    print(f"位置：{base}")


if __name__ == "__main__":
    main()