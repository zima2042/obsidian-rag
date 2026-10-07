"""三种生成后端对比基准测试：商汤 vs OpenRouter免费 vs 本地。
用法: python benchmark.py   → 输出对比 + 保存 benchmark_results.json
"""
import time, json, os
from pathlib import Path
from openai import OpenAI
from query import retrieve, build_context
from config import (SENSENOVA_BASE, GEN_MODEL, sensenova_key,
                    GEN_MODEL_FALLBACK)

QUESTIONS = [
    "什么是RAG？",
    "RAG的核心流程有哪些步骤？",
    "中文向量模型推荐用什么？",
]

BACKENDS = [
    ("商汤 sensenova-6.8-flash-lite", "sensenova"),
    ("OpenRouter免费 GLM-5.2", "openrouter"),
    ("本地 qwen3.5:9b", "local"),
]

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "z-ai/glm-5.2:free"


def _or_key() -> str:
    p = Path.home() / "AppData/Local/hermes/.env"
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def ask(backend: str, q: str, ctx: str):
    t0 = time.time()
    if backend == "sensenova":
        client = OpenAI(api_key=sensenova_key(), base_url=SENSENOVA_BASE)
        model = GEN_MODEL
    elif backend == "openrouter":
        client = OpenAI(api_key=_or_key(), base_url=OPENROUTER_BASE)
        model = OPENROUTER_MODEL
    else:
        from ollama import chat as o_chat
        r = o_chat(model=GEN_MODEL_FALLBACK, messages=[
            {"role": "system", "content": "你是知识库助手，基于给定上下文回答。"},
            {"role": "user", "content": f"知识库内容:\n{ctx}\n\n问题: {q}"},
        ], options={"num_predict": 500}, think=False)
        return time.time() - t0, r["message"]["content"], "ok"

    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system",
             "content": "你是知识库助手，基于给定上下文回答。上下文不足时如实说明，不要编造。"},
            {"role": "user", "content": f"知识库内容:\n{ctx}\n\n问题: {q}"},
        ],
        max_tokens=400,
    )
    return time.time() - t0, r.choices[0].message.content, "ok"


def main():
    results = []
    for q in QUESTIONS:
        hits = retrieve(q)
        ctx = build_context(hits)
        srcs = [m["source"] for m in hits["metadatas"][0]]
        print(f"\n### 问题: {q}")
        print(f"  召回来源: {srcs}")
        for label, backend in BACKENDS:
            try:
                dt, ans, st = ask(backend, q, ctx)
                results.append({"q": q, "backend": label, "dt": round(dt, 1),
                                "len": len(ans), "status": st, "answer": ans})
                print(f"  [{label}] {dt:.1f}s, {len(ans)}字符, 状态={st}")
                print(f"    > {ans[:100].replace(chr(10), ' ')}...")
            except Exception as e:
                results.append({"q": q, "backend": label, "dt": -1, "len": -1,
                                "status": f"FAIL: {type(e).__name__}: {str(e)[:80]}", "answer": ""})
                print(f"  [{label}] FAIL: {type(e).__name__}: {str(e)[:80]}")
    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n结果已保存 benchmark_results.json")


if __name__ == "__main__":
    main()
