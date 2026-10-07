"""数据计算引擎：从笔记/检索结果中提取结构化数据做精确计算。

设计目的：
1. 只依据知识库里的真实数据计算（不编造）
2. 用 Python 精确计算数字（避免 LLM 四则运算出错）
3. 返回 {计算过程, 计算结果}，供 LLM 组织成自然语言回答

触发条件：问题中包含计算意图关键词 + 笔记中有可计算的数据表。
"""
import re
from pathlib import Path

# 计算意图关键词 → 触发类型
CALC_TRIGGERS = {
    "课时": "count_class",
    "节课": "count_class",
    "几节课": "count_class",
    "多少课": "count_class",
    "学分": "sum_credit",
    "总学分": "sum_credit",
    "绩点": "calc_gpa",
    "平均": "avg",
    "平均分": "avg_score",
    "平均成绩": "avg_score",
    "合计": "sum",
    "总共": "sum",
    "一共": "sum",
    "几天": "days",
    "多少天": "days",
    "截止": "deadline",
}


def detect_calc_intent(question: str) -> str | None:
    """检测问题是否包含计算意图，返回计算类型或 None。"""
    for word, calc_type in CALC_TRIGGERS.items():
        if word in question:
            return calc_type
    return None


def extract_tables(text: str) -> list[list[list[str]]]:
    """从 Markdown 文本中提取表格（每张表 → 行 → 单元格）。"""
    tables = []
    current = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            # 跳过分隔行 |---|---|
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            current.append(cells)
        else:
            if current:
                tables.append(current)
                current = []
    if current:
        tables.append(current)
    return tables


def _num(s: str) -> float | None:
    """提取字符串中的第一个数字（支持小数）。"""
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def count_class(rows: list[list[str]]) -> dict:
    """统计每周课时数（按课表表的星期列统计非空格）。"""
    # 找表头：包含"星期一"等的行
    weekday_idx = None
    header_row = None
    for ri, row in enumerate(rows):
        joined = " ".join(row)
        if "星期" in joined:
            header_row = ri
            weekday_idx = [i for i, c in enumerate(row) if "星期" in c or c in ("周一", "周二", "周三", "周四", "周五", "周六", "周日")]
            break
    if header_row is None or not weekday_idx:
        return {"found": False, "reason": "未找到课表星期表头"}
    # 统计每列非空（有课）
    counts = {}
    total = 0
    for wi in weekday_idx:
        day_name = rows[header_row][wi]
        # 该列非空行数（跳过表头）
        n = 0
        for row in rows[header_row + 1:]:
            if wi < len(row) and row[wi].strip() and row[wi] != "&nbsp;":
                n += 1
        counts[day_name] = n
        total += n
    return {"found": True, "per_day": counts, "total_sections": total,
            "note": "按节次统计（1,2节=1个节次段）"}


def sum_column(rows: list[list[str]], target_col: str = "") -> dict:
    """对表格某列求和（默认找'学分'列）。"""
    if not rows:
        return {"found": False, "reason": "无表格数据"}
    header = rows[0]
    col_idx = None
    for i, c in enumerate(header):
        if target_col in c or (not target_col and "学分" in c):
            col_idx = i
            break
    if col_idx is None:
        return {"found": False, "reason": f"未找到'{target_col or '学分'}'列"}
    values = []
    for row in rows[1:]:
        if col_idx < len(row):
            v = _num(row[col_idx])
            if v is not None:
                values.append(v)
    if not values:
        return {"found": False, "reason": "该列没有数字数据"}
    return {"found": True, "values": values, "total": round(sum(values), 2),
            "count": len(values), "column": header[col_idx]}


def avg(rows: list[list[str]] | None, text: str) -> dict:
    """计算平均分/平均值（从文本提取所有数字求平均）。"""
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text) if float(x) < 200]  # 过滤非分数
    if not nums:
        return {"found": False, "reason": "没有可计算的数字"}
    return {"found": True, "values": nums, "avg": round(sum(nums) / len(nums), 2),
            "count": len(nums)}


def calc(calc_type: str, question: str, notes_text: str) -> dict:
    """主入口：根据计算类型对笔记文本执行计算。"""
    tables = extract_tables(notes_text)
    if calc_type in ("count_class",):
        # 课表：表头是星期，行是节次
        for rows in tables:
            r = count_class(rows)
            if r.get("found"):
                return {**r, "calc_type": calc_type}
        return {"calc_type": calc_type, "found": False, "reason": "课表中没有课程数据（可能学期未开始）"}
    if calc_type == "sum_credit":
        for rows in tables:
            r = sum_column(rows, "学分")
            if r.get("found"):
                return {**r, "calc_type": calc_type}
        # 退而求其次：文本中所有伴随"学分"的数字求和
        nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*学分", notes_text)]
        if nums:
            return {"calc_type": calc_type, "found": True, "values": nums,
                    "total": round(sum(nums), 2), "count": len(nums),
                    "note": "从文本提取'X学分'模式求和"}
        return {"calc_type": calc_type, "found": False, "reason": "没有学分数据"}
    if calc_type in ("avg", "avg_score"):
        r = avg(None, notes_text)
        return {**r, "calc_type": calc_type}
    if calc_type == "sum":
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", notes_text)]
        return {"calc_type": calc_type, "found": bool(nums), "values": nums[:50],
                "total": round(sum(nums), 2) if nums else 0, "count": len(nums)}
    if calc_type == "deadline":
        dates = re.findall(r"\d{4}[-年]\d{1,2}[-月]\d{1,2}日?", notes_text)
        return {"calc_type": calc_type, "found": bool(dates), "dates": dates[:10]}
    return {"calc_type": calc_type, "found": False, "reason": "不支持的计算类型"}


def format_result(result: dict) -> str:
    """把计算结果格式化为 LLM 参考文本。"""
    if not result.get("found"):
        return f"[计算说明] 未能完成计算：{result.get('reason', '无数据')}"
    ct = result.get("calc_type", "")
    if ct == "count_class":
        per = "、".join(f"{k}{v}节" for k, v in result.get("per_day", {}).items())
        return (f"[计算说明] 每周共 {result['total_sections']} 个节次段。"
                f"各天：{per}。({result.get('note', '')})")
    if ct == "sum_credit":
        return f"[计算说明] 找到 {result['count']} 条学分记录，总计 {result['total']} 学分。明细：{result['values']}"
    if ct in ("avg", "avg_score"):
        return f"[计算说明] 找到 {result['count']} 个数值，平均值 {result['avg']}。数值：{result['values']}"
    if ct == "sum":
        return f"[计算说明] 共 {result['count']} 个数值，合计 {result['total']}。数值：{result['values'][:20]}"
    if ct == "deadline":
        return f"[计算说明] 文本中的日期：{result.get('dates', [])}"
    return str(result)


if __name__ == "__main__":
    # 自测：用示例数据
    test = """# 选课学分统计
| 序号 | 学期 | 课程名 | 学分 |
| 1 | 2025-2026-1 | 高等数学 | 5.5 |
| 2 | 2025-2026-1 | 大学英语 | 3 |
| 3 | 2025-2026-1 | 线性代数 | 2.5 |
"""
    r = calc("sum_credit", "我的总学分是多少", test)
    print(format_result(r))
    test2 = """| 星期一 | 星期二 | 星期三 |
| 高等数学 | | 大学英语 |
| | 物理 | |
"""
    r2 = calc("count_class", "我每周几节课", test2)
    print(format_result(r2))