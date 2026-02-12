#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试日志查找性能优化
"""
import time
import os
import sys
from datetime import datetime

# 模拟优化前的方法
def get_latest_log_old(log_dir):
    import glob
    today_date = datetime.now().date()
    today_log = os.path.join(log_dir, f"MMDVM-{today_date}.log")

    if os.path.exists(today_log) and os.path.getsize(today_log) > 0:
        return today_log

    log_files = [
        f for f in glob.glob(os.path.join(log_dir, "MMDVM-*.log"))
        if os.path.isfile(f) and os.path.getsize(f) > 0
    ]
    return max(log_files, key=os.path.getmtime) if log_files else None

# 优化后的方法
def get_latest_log_new(log_dir):
    import glob
    # 优先尝试 UTC 时间
    utc_date = datetime.utcnow().date()
    utc_log = os.path.join(log_dir, f"MMDVM-{utc_date}.log")
    if os.path.exists(utc_log) and os.path.getsize(utc_log) > 0:
        return utc_log

    # Fallback 1: 本地时间
    local_date = datetime.now().date()
    if local_date != utc_date:
        local_log = os.path.join(log_dir, f"MMDVM-{local_date}.log")
        if os.path.exists(local_log) and os.path.getsize(local_log) > 0:
            return local_log

    # Fallback 2: glob 查找
    log_files = [
        f for f in glob.glob(os.path.join(log_dir, "MMDVM-*.log"))
        if os.path.isfile(f) and os.path.getsize(f) > 0
    ]
    return max(log_files, key=os.path.getmtime) if log_files else None

def benchmark(func, log_dir, iterations=1000):
    """性能测试"""
    start = time.time()
    for _ in range(iterations):
        result = func(log_dir)
    elapsed = time.time() - start
    return elapsed, result

if __name__ == "__main__":
    log_dir = "/var/log/pi-star"

    print("=" * 60)
    print("日志查找性能测试")
    print("=" * 60)
    print(f"日志目录: {log_dir}")
    print(f"UTC 时间: {datetime.utcnow()}")
    print(f"本地时间: {datetime.now()}")
    print()

    # 测试优化前
    print("[测试 1] 优化前方法")
    time_old, result_old = benchmark(get_latest_log_old, log_dir, 1000)
    print(f"  执行 1000 次耗时: {time_old:.3f}秒")
    print(f"  平均每次: {time_old*1000:.2f}ms")
    print(f"  找到文件: {result_old}")
    print()

    # 测试优化后
    print("[测试 2] 优化后方法")
    time_new, result_new = benchmark(get_latest_log_new, log_dir, 1000)
    print(f"  执行 1000 次耗时: {time_new:.3f}秒")
    print(f"  平均每次: {time_new*1000:.2f}ms")
    print(f"  找到文件: {result_new}")
    print()

    # 对比
    print("=" * 60)
    print("性能对比")
    print("=" * 60)
    if time_old > 0:
        speedup = time_old / time_new
        saved = time_old - time_new
        print(f"  加速比: {speedup:.1f}x")
        print(f"  节省时间: {saved:.3f}秒 (1000次)")
        print(f"  每天节省: {saved * 17.28:.1f}秒 (17,280次)")
        print(f"  CPU 占用降低: {(1 - time_new/time_old)*100:.1f}%")

    # 验证结果一致性
    print()
    print("=" * 60)
    print("结果验证")
    print("=" * 60)
    if result_old == result_new:
        print("  ✓ 两种方法返回相同结果")
    else:
        print("  ✗ 警告：结果不一致！")
        print(f"    优化前: {result_old}")
        print(f"    优化后: {result_new}")
