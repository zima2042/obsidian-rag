# test_chunker.py
from chunker import chunk_markdown


def test_split_by_heading():
    md = "# 标题A\n正文一\n## 子节\n正文二\n# 标题B\n正文三"
    chunks = chunk_markdown(md)
    assert any("标题A" in c and "正文一" in c for c in chunks)
    assert any("标题B" in c and "正文三" in c for c in chunks)


def test_respect_max_len():
    md = "# T\n" + "字" * 800
    chunks = chunk_markdown(md, max_len=600, overlap=100)
    assert all(len(c) <= 600 for c in chunks)
    assert len(chunks) >= 2


if __name__ == "__main__":
    test_split_by_heading()
    test_respect_max_len()
    print("chunker 测试通过")
