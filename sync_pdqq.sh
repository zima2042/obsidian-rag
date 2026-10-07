#!/bin/bash
# QQ频道 + 学院 每日同步脚本
# 用法: bash sync_pdqq.sh  → 抓取增量 → 导入 → 重建索引
# 前置: pdqq_state.json 有效（QQ小号登录态）；Ollama 在跑
set -e
cd "$(cd "$(dirname "$0")" && pwd)"

echo "=============================================="
echo "  Obsidian 知识库增量同步"
echo "  $(date '+%Y-%m-%d %H:%M')"
echo "=============================================="

# --- 1) 检查 Ollama ---
echo "[1/5] 检查 Ollama 服务..."
if ! curl -s --max-time 3 http://127.0.0.1:11434/ >/dev/null 2>&1; then
    echo "  [错误] Ollama 未运行！请先启动: ollama serve"
    exit 1
fi
echo "  OK"

# --- 2) 检查 QQ 登录态 ---
echo "[2/5] 检查 QQ 登录态..."
if [ ! -f pdqq_state.json ]; then
    echo "  [错误] pdqq_state.json 不存在，请先运行: python login_pdqq.py 扫码登录"
    exit 1
fi
echo "  OK"

# --- 3) 爬取 QQ 频道增量 ---
# 注意: 不要用 `| tail` 包住爬虫——tail 会缓冲全部输出，>10 分钟看不到任何进度，
# 看起来像卡死（实际是在跑）。改为写日志文件 + 实时显示尾部摘要。
echo "[3/5] 爬取 QQ 频道增量..."
.venv/Scripts/python pdqq_crawler.py --limit 30 > logs/pdqq_crawl.log 2>&1
CRAWL_EXIT=$?
tail -3 logs/pdqq_crawl.log
if [ $CRAWL_EXIT -ne 0 ]; then
    echo "  [警告] QQ 频道爬取失败（退出码 $CRAWL_EXIT，见 logs/pdqq_crawl.log）"
    echo "  可能原因：登录态过期 → 运行: python login_pdqq.py 重新扫码"
fi
.venv/Scripts/python import_pdqq.py 2>&1 | tail -2

# --- 4) 爬取学院公告增量 ---
echo "[4/5] 爬取学院公告..."
.venv/Scripts/python college_crawler.py --all --pages 3 2>&1 | tail -3 || true
.venv/Scripts/python import_college.py 2>&1 | tail -2

# --- 5) 重建索引 ---
echo "[5/5] 重建向量索引..."
.venv/Scripts/python index.py --force 2>&1 | tail -2

echo ""
echo "=============================================="
echo "  同步完成！ $(date '+%Y-%m-%d %H:%M')"
echo "=============================================="