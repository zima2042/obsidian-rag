"""Markdown 分块：先按标题切段，段过长再按定长切。"""
import re


def chunk_markdown(text: str, max_len: int = 600, overlap: int = 100) -> list[str]:
    text = text.strip()
    if not text:
        return []
    # 按 1-4 级标题切段，标题保留在块首
    blocks = re.split(r"(?m)^(?=#{1,4} )", text)
    chunks = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        while len(b) > max_len:
            chunks.append(b[:max_len])
            b = b[max_len - overlap:]
        if b:
            chunks.append(b)
    return chunks
