# Obsidian RAG 知识库问答

把本地 Obsidian 笔记库变成可问答的知识库：Markdown 分块 → 向量检索 → 大模型回答。
纯本地运行，云端与本地模型自动降级，带 Web 界面与 PWA。

## 功能

- **增量索引**：Markdown 笔记分块写入 ChromaDB（bge-m3 向量，1024 维）
- **混合检索**：向量召回 + 关键词同义词扩展（例如「保研」自动扩展为「推免研究生 推荐免试」）
- **多模型降级链**：云端网关 → 本地 Ollama；遇到 429 / 超时 / 报错自动切下一个
- **Web 界面**：果冻玻璃双主题，手机可装为 PWA，显示知识库最近更新时间
- **可选爬虫**：QQ 频道内容、校内公告的增量抓取与导入

## 快速开始

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows；Linux/macOS 用 source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env              # 填自己的路径与配置
ollama pull bge-m3                # 本地向量模型

python index.py                   # 首次全量建索引
python -m uvicorn server:app --host 0.0.0.0 --port 8777
```

浏览器打开 `http://localhost:8777`。

## 配置

所有配置走环境变量（`.env`，见 `.env.example`）：

| 变量 | 说明 |
| --- | --- |
| `VAULT_PATH` | Obsidian 库路径 |
| `COLLEGE_FOLDER` | 学院笔记的目录名 |
| `QQ_CHANNEL_NAME` / `QQ_CHANNEL_URL` | QQ 频道名称与地址（可选爬虫） |
| `JW_BASE` / `COLLEGE_BASE` | 校内站点地址（可选爬虫） |
| `USER_NAME` / `USER_STUDENT_ID` 等 | 用于「我/我的」检索扩展 |
| `SENSENOVA_K7_API_KEY` | 云端生成模型 key（可选） |

## 项目结构

```
config.py            配置、模型链、同义词扩展
index.py             索引构建（分块 → 向量）
server.py            FastAPI 服务（检索 + 生成 + 统计）
crawler.py           校内公告爬虫（可选）
college_crawler.py   学院官网爬虫（可选）
pdqq_crawler.py      QQ 频道爬虫（可选）
import_*.py          爬取结果导入 Obsidian
sync_*.sh            定时同步脚本
health_check.ps1     服务健康检查（Windows）
static/              Web 前端（HTML/CSS/JS + PWA）
```

## 说明

爬虫模块依赖目标站点结构，默认值均为 `example.edu.cn` 占位符，
需在 `.env` 中配置为实际地址后才可使用；不配置时仅使用索引与问答功能。

## 许可

MIT
