#!/usr/bin/env bash
# 每日同步教务系统公告到 Obsidian 知识库
#
# 增量更新语义 (满足 "每天只更新不删除以前消息"):
#   - 爬虫按 url 去重, 已抓过正文的条目本轮跳过 (不删历史)
#   - 导入按标题写入 vault, 已存在的 .md 自动加后缀不覆盖
#   - 向量索引每次全量重建 (ChromaDB 无增量)
#
# 前置: 1) Sangfor VPN 已连接  2) Ollama 服务运行中
# 用法: bash sync_notices.sh
set -e
cd "$(cd "$(dirname "$0")" && pwd)"

PY=.venv/Scripts/python.exe

echo "=== [0/4] 检查 Ollama 服务 ==="
if ! curl -s --max-time 5 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    echo "  Ollama 未运行, 尝试启动..."
    (ollama serve >/dev/null 2>&1 &) || true
    sleep 5
fi
if curl -s --max-time 5 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    echo "  Ollama OK"
else
    echo "  [错误] Ollama 无法启动, 请手动运行 'ollama serve'"
    exit 1
fi

echo "=== [1/4] 检查 VPN 连通性 ==="
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${JW_BASE:-http://jw.example.edu.cn}/" 2>/dev/null || echo 000)
if [ "$code" != "200" ]; then
    echo "  [错误] 教务处网站不可达 (HTTP $code)"
    echo "  请检查 Sangfor VPN 是否已连接, 稍后重试"
    exit 1
fi
echo "  网站可达 (HTTP $code)"

echo "=== [2/4] 爬取近 6 个月公告 (增量, 跳过已抓) ==="
$PY crawler.py --section tzgg --months 6 --limit 60 --max-pages 15

echo "=== [3/4] 导入 vault (教务在线/通知公告/) ==="
$PY import_notices.py --section tzgg

echo "=== [4/4] 重建向量索引 ==="
$PY index.py --force

echo ""
echo "=== 同步完成 $(date '+%Y-%m-%d %H:%M') ==="
