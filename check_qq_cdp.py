"""检查 QQ 进程命令行参数，确认是否支持 CDP；并探测常见调试端口。"""
import subprocess
import socket

# 1. 查 QQ 命令行
ps = r"Get-CimInstance Win32_Process -Filter \"Name='QQ.exe'\" | Select-Object ProcessId, CommandLine | Format-List"
r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
print("=== QQ 命令行 ===")
print(r.stdout[:1500])

# 2. 探测常见 CDP 端口
print("\n=== 探测调试端口 ===")
for port in [9222, 9223, 9229, 9333, 5555]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port))
        print(f"  :{port} 开放")
    except Exception:
        print(f"  :{port} 关闭")
    finally:
        s.close()