"""Kill process on port 8010 using psutil - scan all connections."""
import psutil
import time

PORT = 8010

print(f"扫描所有连接，查找端口 {PORT}...")
found = False
for proc in psutil.process_iter(['pid', 'name', 'username']):
    try:
        for conn in proc.net_connections(kind='inet'):
            if conn.laddr and conn.laddr.port == PORT:
                print(f"找到进程: PID={proc.pid} name={proc.name()}")
                print(f"  正在终止...")
                proc.terminate()
                time.sleep(3)
                if proc.is_running():
                    print(f"  强制杀死...")
                    proc.kill()
                    time.sleep(1)
                if not proc.is_running():
                    print(f"  成功终止 PID={proc.pid}")
                else:
                    print(f"  终止失败，进程仍在运行")
                found = True
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
        pass

if not found:
    print(f"未找到占用端口 {PORT} 的进程")

# Also try directly by PID 33468
print("\n直接尝试终止 PID=33468...")
try:
    p = psutil.Process(33468)
    print(f"  找到: {p.name()} (status={p.status()})")
    p.terminate()
    time.sleep(2)
    if p.is_running():
        p.kill()
        time.sleep(1)
    print(f"  结果: {'已终止' if not p.is_running() else '仍运行中'}")
except psutil.NoSuchProcess:
    print("  PID=33468 不存在（可能已退出）")
except psutil.AccessDenied:
    print("  拒绝访问（需要管理员权限）")
