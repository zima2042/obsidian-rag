"""把爬取结果导入 Obsidian vault，按栏目归档，frontmatter 保留来源元数据。

用法: python import_notices.py [--input crawled_data.json] [--section tzgg]
"""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from config import VAULT_PATH

SECTION_NAMES = {
    "tzgg": "通知公告",
    "jxgg": "教学公告",
    "ksa": "考试工作",
}
# vault 内目录名（中文，便于人翻）
FOLDER = "教务在线"


def safe_filename(title: str) -> str:
    """清理 Windows 非法字符，长度截断。"""
    s = re.sub(r'[\\/:*?"<>|]', "-", title).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:60] or "未命名"


def import_to_vault(data: list[dict], section: str) -> int:
    folder = VAULT_PATH / FOLDER / SECTION_NAMES.get(section, section)
    folder.mkdir(parents=True, exist_ok=True)

    # 统计该目录已有文件数，用于同名去重
    count = 0
    for it in data:
        md = (it.get("markdown") or it.get("body") or "").strip()
        if not md:
            continue
        title = it.get("title", "未命名")
        base = safe_filename(title)
        fpath = folder / f"{base}.md"
        n = 1
        while fpath.exists():
            n += 1
            fpath = folder / f"{base}_{n}.md"

        # frontmatter：Obsidian 可索引，检索来源可追溯
        meta = {
            "title": title.replace('"', "'"),
            "source": "学校教务处",
            "url": it.get("url", ""),
            "published": it.get("date", ""),
            "fetched_at": it.get("fetched_at", ""),
            "section": SECTION_NAMES.get(section, section),
            "tags": ["教务在线", SECTION_NAMES.get(section, section)],
        }
        fm = "---\n" + "".join(f"{k}: {v}\n" for k, v in meta.items()) + "---\n\n"
        fpath.write_text(fm + md + "\n", encoding="utf-8")
        count += 1

    print(f"导入完成：{count} 篇 → {folder}")
    return count


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="crawled_data.json")
    p.add_argument("--section", default="tzgg")
    a = p.parse_args()

    f = Path(__file__).parent / a.input
    if not f.exists():
        print(f"找不到 {f}，请先运行 crawler.py")
        return
    data = json.loads(f.read_text(encoding="utf-8"))
    has_body = [it for it in data if (it.get("markdown") or it.get("body"))]
    print(f"读取 {len(data)} 条，其中有正文 {len(has_body)} 条")
    import_to_vault(has_body, a.section)


if __name__ == "__main__":
    main()
