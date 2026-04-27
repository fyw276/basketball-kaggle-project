"""Kill backend on port 8010."""
import psutil
import time

for proc in psutil.process_iter(['pid', 'name']):
    try:
        for conn in proc.net_connections(kind='inet'):
            if conn.laddr and conn.laddr.port == 8010:
                print(f"终止 PID={proc.pid} ({proc.name()})")
                proc.terminate()
                time.sleep(2)
                if proc.is_running():
                    proc.kill()
                    time.sleep(1)
                print(f"  {'已终止' if not proc.is_running() else '仍运行'}")
                exit(0)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
print("未找到占用 8010 的进程")
