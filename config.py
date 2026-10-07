"""统一配置：路径、分块参数、模型链、API key 自动加载、查询同义词扩展。

关键点：商汤 token.sensenova.cn 是统一网关，一个 key 可调用多个模型
（deepseek / glm / sensenova），所以三级降级只切 model 名，base_url 和 key 不变。
"""
from pathlib import Path
import os
import sys

# ---- 提前加载 .env（VAULT_PATH / USER_* 需在下方模块级常量前就读到）----
for _p in (Path(__file__).parent / ".env", Path.home() / "AppData/Local/hermes/.env"):
    if _p.exists():
        for _line in _p.read_text(encoding="utf-8").splitlines():
            if "=" in _line and not _line.lstrip().startswith("#"):
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ---- 路径（支持 PyInstaller 打包模式）----
# PyInstaller --onefile 模式下，sys._MEIPASS 是资源解压的临时目录
# 但数据文件（ChromaDB）应该放在 exe 旁边的持久化目录，不放在 _MEIPASS
if getattr(sys, "frozen", False):
    # 打包模式：exe 所在目录（持久化数据）+ _MEIPASS（临时解压的静态文件）
    APP_ROOT = Path(sys.executable).parent
    DATA_DIR = APP_ROOT / "data"
    STATIC_DIR = Path(sys._MEIPASS) / "static"
else:
    # 开发模式：当前文件所在目录
    APP_ROOT = Path(__file__).parent
    DATA_DIR = APP_ROOT / "data"
    STATIC_DIR = APP_ROOT / "static"

VAULT_PATH = Path(os.environ.get("VAULT_PATH") or (Path.home() / "Documents" / "Obsidian Vault"))
COLLECTION = "obsidian_kb"

# ---- 分块参数 ----
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
TOP_K = 10                 # 回答时参考的分块数

# ---- 本地模型 ----
EMBED_MODEL = "bge-m3"                 # Ollama embedding（1024 维）
OLLAMA_URL = "http://localhost:11434"
LOCAL_FALLBACK = "qwen3.5:9b"          # 本地兜底生成

# ---- 云端统一网关 ----
CLOUD_BASE = "https://token.sensenova.cn/v1"
CLOUD_KEY_ENV = "SENSENOVA_K7_API_KEY"

# ---- 生成模型链（按优先级，429/失败自动切下一个）----
CLOUD_CHAIN = ["deepseek-v4-flash", "glm-5.2", "sensenova-6.8-flash-lite"]

# 兼容旧接口
GEN_MODEL = CLOUD_CHAIN[0]

# ---- 前端模型选择器（key=实际模型名, label=显示名, backend=cloud/local）----
# auto = 按 CLOUD_CHAIN 自动降级，最后兜底本地
CLOUD_MODELS = [
    {"key": "auto",                   "label": "自动（首选 DeepSeek）", "backend": "cloud", "desc": "四级降级"},
    {"key": "deepseek-v4-flash",      "label": "DeepSeek V4 Flash",     "backend": "cloud", "desc": "快速"},
    {"key": "glm-5.2",                "label": "GLM 5.2",               "backend": "cloud", "desc": "均衡"},
    {"key": "sensenova-6.8-flash-lite", "label": "SenseNova",           "backend": "cloud", "desc": "商汤"},
    {"key": "qwen3.5:9b",             "label": "本地 Qwen3.5 9B",       "backend": "local", "desc": "离线"},
]

# ---- 用户身份（提问中"我/我的" = 本人）----
# 检索时把"我"扩展为身份词，命中个人信息笔记（学籍/课表/成绩）
USER_IDENTITY = {
    "name": os.environ.get("USER_NAME", "示例用户"),
    "student_id": os.environ.get("USER_STUDENT_ID", "0000000000"),
    "major": os.environ.get("USER_MAJOR", "示例专业类"),
    "college": os.environ.get("USER_COLLEGE", "示例学院"),
    "class_name": os.environ.get("USER_CLASS", "00000000班"),
}

# ---- 关键词同义词扩展 ----
# 用户口语词 → 知识库正式术语，检索时把口语词替换/补充为术语，提高召回率
# 例：用户问"保研"→ 扩展为"推免研究生 推荐免试"，因为公告里用的是正式术语
QUERY_EXPANSIONS = {
    "保研": "推免研究生 推荐免试",
    "推免": "推免研究生 推荐免试",
    "考研": "全国研究生招生 推免研究生",
    "绩点": "GPA 平均学分绩点 绩点统计",
    "GPA": "平均学分绩点 绩点统计",
    "转专业": "专业分流 转专业申请",
    "分流": "专业分流 大类招生",
    "选课": "补改选课 重修免修",
    "补选": "补改选课",
    "补考": "补缓考 重修免修",
    "重修": "重修免修 补考",
    "免修": "重修免修 外语免修申请",
    "学分": "学分统计 学分认定 选课学分",
    "考试": "课程考核 期末考试 考试安排 准考证",
    "期末": "期末课程考核 期末考试",
    "挂科": "未通过 补考 重修",
    "毕设": "毕业设计 毕业论文",
    "毕业论文": "毕业设计 毕业论文 毕设",
    "毕业": "毕业审核 毕业资格 毕设",
    "奖学金": "奖助学金 奖学金评定",
    "奖助": "奖助学金",
    "助学贷款": "奖助学金 助学贷款",
    "四六级": "大学英语四六级 英语专业",
    "计算机等级": "计算机等级考试 NCRE",
    "体测": "体质健康测试",
    "体育": "体育分项 体质健康测试",
    "就业": "就业创业 就业指导",
    "实习": "实习 实践教学 劳动教育",
    "劳动": "劳动教育",
    "辅修": "辅修专业",
    "辅修专业": "辅修专业报名",
    "学籍": "学籍信息 学籍异动",
    "成绩单": "成绩考核 成绩与排名",
    "排名": "成绩与排名 排名及绩点",
    "绩点统计": "成绩与排名 排名及绩点统计",
    "调课": "调停课 调停课查询",
    "停课": "调停课",
    "教材": "教材信息",
    "授课计划": "授课计划 课程教学大纲",
    "课表": "课表查询 学生课表",
    "成绩": "成绩考核 成绩与排名 成绩认定",
    "外语": "大学英语四六级 外语免修",
    "创新创业": "创新创业 素质拓展学分 孵化基地",
    "实践": "实践教学 劳动教育 创新创业",
}


def _load_dotenv():
    """从 Hermes .env 自动读取所有 *_KEY 环境变量。"""
    p = Path.home() / "AppData/Local/hermes/.env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k.endswith("_KEY") or "API" in k:
            os.environ.setdefault(k, v)


_load_dotenv()


def cloud_key() -> str:
    """返回商汤网关 key；找不到则抛错。"""
    key = os.environ.get(CLOUD_KEY_ENV, "")
    if not key:
        raise RuntimeError(f"未找到环境变量 {CLOUD_KEY_ENV}，请检查 AppData/Local/hermes/.env")
    return key


# 兼容旧代码调用
def sensenova_key() -> str:
    return cloud_key()
