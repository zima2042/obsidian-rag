"""把教务系统个人信息页转成 Obsidian 笔记并入库。

输入：personal_data.json（由 personal_crawler.py 抓取）
输出：Obsidian Vault/教务在线/个人信息/*.md
每页一篇笔记，带 frontmatter 元数据，方便检索。
"""
import os
import json
from datetime import datetime
from pathlib import Path

VAULT = Path(os.environ.get("OBSIDIAN_VAULT") or (Path.home() / "Documents" / "Obsidian Vault"))
PERSONAL_DIR = VAULT / "教务在线" / "个人信息"
SRC = Path(__file__).parent / "personal_data.json"

# 页面 key → (文件名, 标题)
PAGE_NAMES = {
    "home": ("个人信息主页", "个人信息主页"),
    "xj": ("学籍信息", "学籍信息"),
    "zc": ("注册信息", "注册信息"),
    "cj": ("成绩考核", "成绩考核"),
    "cjp": ("成绩与排名", "成绩与排名"),
    "xkxf": ("选课学分统计", "选课学分统计"),
    "kb": ("课表查询", "课表查询"),
    "ksap": ("考试安排", "考试安排"),
    "byxf": ("毕业学分学费", "毕业学分学费"),
    "skjh": ("授课计划", "授课计划"),
    "jiaocai": ("教材信息", "教材信息"),
}


def sanitize_filename(name: str) -> str:
    """去掉文件名非法字符。"""
    return name.replace("\\", "/").replace("/", "-").replace("\x08", "")


def main() -> int:
    if not SRC.exists():
        print(f"[错误] 未找到 {SRC}")
        print("       请先运行: python personal_crawler.py")
        return 0

    data = json.loads(SRC.read_text(encoding="utf-8"))
    PERSONAL_DIR.mkdir(parents=True, exist_ok=True)

    written = 0
    for key, item in data.items():
        title = item.get("name") or PAGE_NAMES.get(key, ("未命名", "未命名"))[1]
        fname = sanitize_filename(title) + ".md"
        text = item.get("text", "").strip()

        if len(text) < 10:
            # 内容太少（可能页面为空或跳转），跳过
            print(f"  跳过 {title}（内容仅 {len(text)} 字）")
            continue

        # frontmatter
        fm = [
            "---",
            f'title: "{title}"',
            f'page_key: "{key}"',
            f'source: "{item.get("url", "")}"',
            f'fetched_at: "{item.get("fetched_at", "")}"',
            'category: "教务在线"',
            'type: "个人信息"',
            "---",
            "",
            f"# {title}",
            "",
        ]

        content = "\n".join(fm) + text
        (PERSONAL_DIR / fname).write_text(content, encoding="utf-8")
        written += 1
        print(f"  写入 {fname} ({len(text)} 字)")

    print(f"\n完成：{written} 篇个人信息笔记 → {PERSONAL_DIR}")
    return written


if __name__ == "__main__":
    main()
