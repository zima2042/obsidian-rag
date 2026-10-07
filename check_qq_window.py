"""检查 QQ 窗口标题，判断是否在登录界面。"""
import ctypes
import subprocess

# 用 powershell 获取窗口标题（通过文件避免转义）
ps = r'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$proc = Get-Process QQ -ErrorAction SilentlyContinue | Select-Object -First 1
if ($proc) {
    Write-Output ("MainWindowTitle=[" + $proc.MainWindowTitle + "]")
    Write-Output ("Responding=" + $proc.Responding)
} else {
    Write-Output "no QQ process"
}
'''
r = subprocess.run(["powershell", "-Command", ps], capture_output=True, text=True, timeout=20)
print(r.stdout.strip() or r.stderr.strip()[:300])