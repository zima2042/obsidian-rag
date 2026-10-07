"""把学院爬取结果导入 Obsidian vault。

输入: crawled_college.json（college_crawler.py 生成）
输出: Obsidian Vault/学院/<栏目>/<标题>.md
格式与教务在线一致：frontmatter + 标题 + 正文
"""
import json
import os
import re
from pathlib import Path

from config import VAULT_PATH

FOLDER = os.environ.get("COLLEGE_FOLDER", "学院")
DATA_FILE = Path(__file__).parent / "crawled_college.json"


def safe_filename(title: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "-", title).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:60] or "未命名"


def main():
    if not DATA_FILE.exists():
        print("未找到 crawled_college.json，请先运行 college_crawler.py")
        return

    items = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    print(f"共 {len(items)} 条")

    base = VAULT_PATH / FOLDER
    count = 0
    skipped = 0
    for it in items:
        section = (it.get("section") or "通知公告").strip()
        title = safe_filename(it.get("title", "未命名"))
        folder = base / section
        folder.mkdir(parents=True, exist_ok=True)

        target = folder / f"{title}.md"
        if target.exists():
            skipped += 1
            continue

        meta = "\n".join([
            "---",
            f'title: "{it.get("title", "未命名")}"',
            f'source: "{FOLDER}:{section}"',
            f'url: "{it.get("url", "")}"',
            f'date: "{it.get("date", "")}"',
            f'fetched_at: "{it.get("fetched_at", "")}"',
            f'section: "{section}"',
            'type: "学院公告"',
            "---",
            "",
        ])
        body = it.get("body", "").strip()
        md = f"# {it.get('title', '未命名')}\n\n{body}\n"
        target.write_text(meta + md, encoding="utf-8")
        count += 1

    print(f"导入完成：新增 {count} 篇，跳过 {skipped} 篇")
    print(f"位置：{base}")


if __name__ == "__main__":
    main()