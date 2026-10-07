"""Obsidian RAG 服务入口（支持 PyInstaller 打包）。

打包后双击 exe 即可启动服务，无需 Python 环境。
直接复用 server.py 的逻辑（history 上下文、计算引擎、人称映射都在里面），
避免两份代码不同步。

用法：直接运行 obsidian_rag.exe（首次启动会解压到临时目录，稍慢）
"""
import sys
from pathlib import Path


def get_app_dir() -> Path:
    """获取资源目录：
    - PyInstaller 打包模式：sys._MEIPASS（临时解压目录）
    - 开发模式：当前文件所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


APP_DIR = get_app_dir()
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# 复用 server.py 的全部逻辑（路由、计算引擎、上下文对话、人称映射）
from server import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  Obsidian 知识库服务启动")
    print("=" * 50)
    print(f"  浏览器访问: http://127.0.0.1:8777")
    print(f"  局域网访问: http://<本机IP>:8777")
    print("=" * 50)
    print("  按 Ctrl+C 停止服务")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8777)