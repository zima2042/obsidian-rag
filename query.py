"""本地向量检索 + 商汤统一网关多模型降级生成。用法: python query.py "你的问题" [--local]"""
import argparse
import chromadb
from openai import OpenAI
from config import (DATA_DIR, COLLECTION, EMBED_MODEL, LOCAL_FALLBACK,
                    CLOUD_CHAIN, CLOUD_BASE, cloud_key, QUERY_EXPANSIONS,
                    USER_IDENTITY)

# 懒加载单例：PyInstaller 打包时模块级 Client 实例无法 pickle，必须延迟创建
_ollama = None
_client = None


def get_ollama():
    """获取 Ollama 客户端（懒加载）。"""
    global _ollama
    if _ollama is None:
        from ollama import Client
        _ollama = Client(host="http://localhost:11434")
    return _ollama


def get_client():
    """获取商汤网关 OpenAI 客户端（懒加载）。"""
    global _client
    if _client is None:
        _client = OpenAI(api_key=cloud_key(), base_url=CLOUD_BASE, timeout=120)
    return _client


def expand_query(question: str) -> str:
    """用 QUERY_EXPANSIONS 把口语词扩展为知识库正式术语，提高召回率。
    例：'保研需要什么条件' → '保研 推免研究生 推荐免试 需要什么条件'
    '我的专业是什么' → '我的专业是什么 示例用户 0000000000 示例专业类'（命中个人信息笔记）
    """
    expanded = set()
    for word, terms in QUERY_EXPANSIONS.items():
        if word in question:
            expanded.update(terms.split())

    # 人称映射："我/我的" → 用户身份词，命中个人信息笔记
    # 排除"我们/我校/我国/我国/我院"等非个人语境
    has_self = ("我" in question or "本人" in question or "自己" in question)
    not_group = not any(w in question for w in ("我们", "我校", "我国", "我院", "我院学", "咱们"))
    if has_self and not_group:
        uid = USER_IDENTITY
        expanded.update([uid["name"], uid["student_id"], uid["major"], uid["college"]])

    # 保留原词 + 追加扩展词（去重、去空）
    parts = [question] + [t for t in expanded if t not in question]
    return " ".join(parts)


def retrieve(question: str, top_k: int = 10) -> dict:
    """本地向量检索（bge-m3 embedding + ChromaDB）。返回分块+元数据。
    top_k = 参考的「不同文章」数：多取分块，按 source 去重后凑满 top_k 篇。
    """
    col = chromadb.PersistentClient(path=str(DATA_DIR)).get_collection(COLLECTION)
    # 扩展查询词提高召回率
    query = expand_query(question)
    ollama = get_ollama()
    vec = ollama.embed(model=EMBED_MODEL, input=[query])["embeddings"][0]
    # 多取一些分块（每篇通常 1-2 块），再按来源去重
    n_results = max(top_k * 3, 20)
    res = col.query(query_embeddings=[vec], n_results=n_results)

    docs, metas, dists = [], [], []
    seen_sources = set()
    for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        src = m.get("source", "?")
        # 相似度阈值：距离>1.3 视为明显不相关，不纳入（bge-m3 距离越小越相关）
        if dist > 1.3:
            break
        if src in seen_sources:
            continue
        seen_sources.add(src)
        docs.append(d)
        metas.append(m)
        dists.append(dist)
        if len(docs) >= top_k:
            break

    return {"documents": docs, "metadatas": metas, "distances": dists}


def build_context(hits: dict) -> str:
    """把召回分块拼成上下文（标注来源便于追溯）。"""
    parts = []
    for i, (doc, meta) in enumerate(zip(hits["documents"], hits["metadatas"]), 1):
        parts.append(f"[{i}] 来源：{meta.get('source', '?')}\n{doc}")
    return "\n\n---\n\n".join(parts)


def _ask_cloud(model: str, question: str, context: str, history: list | None = None) -> str:
    """调商汤统一网关（一个 key 调多个模型）。429/失败向上抛异常。
    history: [{"role":"user"/"assistant", "content": "..."}] 最近几轮对话，用于上下文理解。
    """
    client = get_client()
    messages = [
        {"role": "system", "content": (
            "你是 Obsidian 知识库助手。只依据下面提供的笔记内容回答，"
            "回答要准确、简洁，必要时用 Markdown 列表。若上下文不足以回答，"
            "请说明知识库中没有相关内容，不要编造。"
            "如果用户正在追问上一轮的问题（例如'那什么时候截止'、'帮我算一下'），"
            "要结合历史对话理解他指的是什么。")},
    ]
    # 插入历史对话（结合上下文用，最多 6 轮）
    if history:
        for h in history[-6:]:
            role = "user" if h.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": h.get("content", "")[:800]})
    messages.append({"role": "user", "content": f"问题：{question}\n\n参考笔记：\n{context}"})
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
    )
    ans = resp.choices[0].message.content or ""
    return ans.strip()


def answer_cloud(question: str, context: str, force_model: str = None, history: list | None = None) -> tuple[str, str]:
    """生成回答。force_model=None 时按 CLOUD_CHAIN 自动降级；指定模型名则直接用该模型（不降级）。

    返回 (回答文本, 实际使用的模型名)。
    """
    if force_model and force_model != "auto" and force_model != LOCAL_FALLBACK:
        # 用户手动选了某个云端模型，直接调用，不降级
        try:
            ans = _ask_cloud(force_model, question, context, history)
            return ans, force_model
        except Exception as e:
            print(f"    [云端失败] {force_model}: {str(e)[:70]}")
            return "", None

    chain = CLOUD_CHAIN if force_model == "auto" else [m for m in CLOUD_CHAIN if m == force_model] or CLOUD_CHAIN
    for model in chain:
        try:
            ans = _ask_cloud(model, question, context, history)
            print(f"    ↳ [{model}] 回答成功")
            return ans, model
        except Exception as e:
            print(f"    ↳ [{model}] 失败/429: {str(e)[:70]} → 切下一个模型")
    return "", None


def answer_local(question: str, context: str, history: list | None = None) -> tuple[str, str]:
    """本地 Ollama 兜底（断网也能用）。必须 think=False 否则 thinking 模式导致空回答。"""
    try:
        ollama = get_ollama()
        messages = [
            {"role": "system", "content": (
                "你是 Obsidian 知识库助手，只依据提供的笔记内容回答，简洁准确。"
                "如果用户正在追问上一轮的问题，要结合历史对话理解他指的是什么。")},
        ]
        if history:
            for h in history[-6:]:
                role = "user" if h.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": h.get("content", "")[:800]})
        messages.append({"role": "user", "content": f"问题：{question}\n\n参考笔记：\n{context}"})
        resp = ollama.chat(
            model=LOCAL_FALLBACK,
            messages=messages,
            options={"temperature": 0.3, "num_predict": 800},
            think=False,
        )
        ans = resp.get("message", {}).get("content", "")
        return ans.strip(), LOCAL_FALLBACK
    except Exception as e:
        print(f"    [本地失败] {e}")
        return "", None


def answer(question: str, context: str, force_local: bool = False, force_model: str = None, history: list | None = None) -> tuple[str, str]:
    """统一入口。
    force_local=True: 强制本地
    force_model: 指定模型名（'auto' 或不传 = 自动降级；云端模型名 = 直接用；本地模型名 = 本地）
    history: 最近几轮对话，用于结合上下文回答。
    """
    if force_local or force_model == LOCAL_FALLBACK:
        return answer_local(question, context, history)
    ans, model = answer_cloud(question, context, force_model=force_model, history=history)
    if not ans or not model:
        # 云端全失败 → 本地兜底
        print("    ↳ 云端全部失败，切本地 Ollama")
        ans, model = answer_local(question, context, history)
    if not ans:
        return "抱歉，云端和本地生成都失败了。请检查网络或 Ollama 服务（ollama serve）。", None
    return ans, model


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default="我 Obsidian 知识库里的笔记讲了什么？")
    ap.add_argument("--local", action="store_true", help="强制本地生成")
    ap.add_argument("--model", default=None, help="指定模型（auto/deepseek-v4-flash/glm-5.2/sensenova-6.8-flash-lite/qwen3.5:9b）")
    a = ap.parse_args()

    print(f"问题：{a.question}")
    hits = retrieve(a.question)
    ctx = build_context(hits)
    print(f"召回 {len(hits['documents'])} 个分块")
    for m in hits["metadatas"]:
        print(f"  - {m['source']}")

    print("\n生成回答...")
    ans, model = answer(a.question, ctx, force_local=a.local, force_model=a.model)
    print(f"\n[模型: {model}]\n{ans}")


if __name__ == "__main__":
    main()
