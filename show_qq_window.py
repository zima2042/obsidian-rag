"""枚举 QQ.exe 的所有窗口并尝试显示主窗口。"""
import ctypes
from ctypes import wintypes
import subprocess

user32 = ctypes.windll.user32

EnumWindows = user32.EnumWindows
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
IsWindowVisible = user32.IsWindowVisible
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
ShowWindow = user32.ShowWindow
SetForegroundWindow = user32.SetForegroundWindow

SW_RESTORE = 9

# 用 PowerShell 拿 QQ PID（避免编码问题）
ps = r"Get-Process QQ -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }"
r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
target_pids = set()
for line in r.stdout.splitlines():
    line = line.strip()
    if line.isdigit():
        target_pids.add(int(line))

print("QQ PIDs:", sorted(target_pids))

results = []

@ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, lparam):
    pid = wintypes.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value in target_pids:
        n = GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        GetWindowTextW(hwnd, buf, n + 1)
        visible = IsWindowVisible(hwnd)
        results.append((hwnd, pid.value, buf.value, visible))
    return True

EnumWindows(cb, 0)
for hwnd, pid, title, vis in results:
    print(f"hwnd={hwnd} pid={pid} visible={vis} title='{title}'")

# 显示所有有标题的窗口
for hwnd, pid, title, vis in results:
    if title and not vis:
        ShowWindow(hwnd, SW_RESTORE)
        print(f"  -> 恢复显示: '{title}'")
if results:
    # 聚焦第一个有标题的
    for hwnd, pid, title, vis in results:
        if title:
            SetForegroundWindow(hwnd)
            print(f"  -> 已置前: '{title}'")
            break
print("DONE")