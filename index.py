"""扫描 Obsidian vault 的 .md，分块后本地向量化并写入 ChromaDB。

关键实现：直接用 ollama Client 算 embedding，再把向量传给 chromadb 的
embeddings 参数 —— 绕过 chromadb 的 OllamaEmbeddingFunction（它的 url 参数
在持久化/反序列化时会丢失，导致 fallback 到随机端口报 "connectex refused"）。
"""
import argparse
import chromadb
from ollama import Client
from config import VAULT_PATH, DATA_DIR, COLLECTION, EMBED_MODEL, OLLAMA_URL
from chunker import chunk_markdown

_ollama = Client(host=OLLAMA_URL, timeout=120)


def embed(texts: list[str]) -> list[list[float]]:
    """用本地 Ollama bge-m3 算 embedding（1024 维）。"""
    return _ollama.embed(model=EMBED_MODEL, input=texts).embeddings


def build_index(force: bool = False) -> int:
    client = chromadb.PersistentClient(path=str(DATA_DIR))
    col = client.get_or_create_collection(COLLECTION)  # 不传 EF，避免序列化问题
    if force:
        existing = col.get()["ids"]
        if existing:
            col.delete(ids=existing)
            print("已清空旧索引")

    docs, ids, metas, embs = [], [], [], []
    md_files = sorted(VAULT_PATH.rglob("*.md"))
    for f in md_files:
        if ".obsidian" in f.parts:
            continue  # 跳过 Obsidian 配置文件
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, c in enumerate(chunk_markdown(text)):
            if not c.strip():
                continue
            docs.append(c)
            ids.append(f"{f.stem}#{i}")
            metas.append({"source": str(f.relative_to(VAULT_PATH))})
    print(f"待向量化 {len(docs)} 个分块，来自 {len(md_files)} 篇笔记")

    # 分批向量化 + 写入，避免一次性把大量文本发给 Ollama 超时
    BATCH = 16
    done = 0
    for s in range(0, len(docs), BATCH):
        batch = docs[s:s + BATCH]
        try:
            vecs = embed(batch)
        except Exception as e:
            print(f"  批次 {s//BATCH} embedding 失败: {str(e)[:60]}，跳过")
            continue
        embs.extend(vecs)
        col.upsert(
            ids=ids[s:s + BATCH],
            documents=batch,
            metadatas=metas[s:s + BATCH],
            embeddings=vecs,
        )
        done += len(batch)
        if done % (BATCH * 5) == 0 or done == len(docs):
            print(f"  进度 {done}/{len(docs)}")

    print(f"索引完成：{len(md_files)} 篇笔记 → {done} 个分块")
    return done


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="清空后重建")
    a = p.parse_args()
    build_index(force=a.force)
