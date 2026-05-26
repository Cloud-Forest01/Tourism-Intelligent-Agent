
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
停止智能规划服务器
查找并终止占用端口 8000 的进程
"""
import subprocess
import sys
import os


def find_processes_on_port(port):
    """查找占用指定端口的进程"""
    try:
        result = subprocess.run(
            f'netstat -ano | findstr ":{port}"',
            shell=True,
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore'
        )

        lines = result.stdout.strip().split('\n')
        processes = []

        for line in lines:
            if 'LISTENING' in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    processes.append(pid)

        return processes
    except Exception as e:
        print(f"[错误] 查找进程失败: {e}")
        return []


def kill_process(pid):
    """终止指定 PID 的进程"""
    try:
        result = subprocess.run(
            f'taskkill /PID {pid} /F',
            shell=True,
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore'
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[错误] 终止进程失败: {e}")
        return False


def main():
    print("=" * 50)
    print(" 停止智能规划服务器")
    print("=" * 50)
    print()

    port = 8000
    print(f"检查端口 {port} 占用情况...")

    processes = find_processes_on_port(port)

    if not processes:
        print(f"端口 {port} 未被占用，服务器可能未运行")
        print()
        print("=" * 50)
        input("按回车键退出...")
        return

    print(f"发现 {len(processes)} 个占用端口的进程")

    success_count = 0
    for pid in processes:
        print(f"  正在终止进程 {pid}...", end=" ")
        if kill_process(pid):
            print("[成功]")
            success_count += 1
        else:
            print("[失败]")

    print()
    print(f"总结: 成功终止 {success_count}/{len(processes)} 个进程")
    print()
    print("=" * 50)
    input("按回车键退出...")


if __name__ == "__main__":
    main()
