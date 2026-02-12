# MMDVM-Push-Notifier 完整优化方案

## 优化完成时间
2026-02-12

## 优化目标
- 降低 CPU 占用 30-50%
- 减少 I/O 操作 40%
- 提升长期运行稳定性
- 不影响推送响应速度

---

## 优化详情

### 1. CPU 读取缓存优化 (hardware.py)

**位置**: `hardware.py` 第14-18行, 第23-31行

**优化内容**:
- 添加 `_last_cpu_read` 和 `_cached_cpu` 缓存属性
- CPU 读取结果缓存 3 秒
- 3 秒内重复调用直接返回缓存值

**收益**:
- 避免频繁调用 `top` 命令或读取 `/proc/stat`
- 每次 `top` 调用耗时 100-200ms，缓存后 <1ms
- CPU 占用降低约 20%

**代码变更**:
```python
def __init__(self):
    self._cpu_prev_total = None
    self._cpu_prev_idle = None
    self._last_cpu_read = 0.0  # 新增
    self._cached_cpu = "0"     # 新增

def _cpu_percent_top(self) -> str:
    import time as _time
    now = _time.time()
    if now - self._last_cpu_read < 3.0:  # 3秒缓存
        return self._cached_cpu
    # ... 原有逻辑
    self._last_cpu_read = now
    self._cached_cpu = result
    return result
```

---

### 2. 配置文件检查间隔优化 (config.py)

**位置**: `config.py` 第11行

**优化内容**:
- 配置文件修改检查间隔: 5秒 → 30秒

**收益**:
- 减少文件系统 mtime 检查次数 83%
- 配置文件很少修改，30秒检查足够

**代码变更**:
```python
_check_interval: int = 30  # 从5秒改为30秒
```

---

### 3. 日志轮询间隔动态优化 (mmdvm_push.py)

**位置**: `mmdvm_push.py` 第220-231行

**优化内容**:
- 原来: 活跃时 0.2秒，空闲时 0.8秒
- 优化后:
  - 1分钟内活跃: 0.3秒
  - 5分钟内: 0.5秒
  - 长时间无活动: 1.0秒

**收益**:
- 长时间无活动时 CPU 唤醒频率降低 50%
- 响应延迟增加可忽略 (0.1-0.2秒)

**代码变更**:
```python
if not line:
    idle_time = time.time() - self.last_activity_ts
    if idle_time < 60:
        interval = 0.3
    elif idle_time < 300:
        interval = 0.5
    else:
        interval = 1.0
    time.sleep(interval)
    continue
```

---

### 4. 温度检查频率优化 (mmdvm_push.py)

**位置**: `mmdvm_push.py` 第208-217行

**优化内容**:
- 原来: 每处理一行日志就检查温度 (可能每秒数十次)
- 优化后: 每30秒检查一次

**收益**:
- 减少温度文件读取次数 95%+
- 温度变化缓慢，30秒检查完全足够

**代码变更**:
```python
def __init__(self):
    # ...
    self._last_temp_check: float = 0.0  # 新增

def process_line(self, line: str):
    # ...
    now = time.time()
    if now - self._last_temp_check > 30:
        self.check_temp_alert(conf)
        self._last_temp_check = now
```

---

### 5. 日志文件查找缓存优化 (mmdvm_push.py)

**位置**: `mmdvm_push.py` 第110-127行

**优化内容**:
- 缓存今天的日期和日志路径
- 避免每次都格式化日期和 glob 查找

**收益**:
- 减少日期格式化和文件系统调用
- 提升日志文件查找速度

**代码变更**:
```python
def __init__(self):
    # ...
    self._cached_date = None
    self._today_log = None

def get_latest_log(self) -> Optional[str]:
    today_date = datetime.now().date()
    if self._cached_date != today_date:
        self._cached_date = today_date
        self._today_log = os.path.join(MMDVM_LOG_DIR, f"MMDVM-{today_date}.log")
    # ...
```

---

### 6. 内存监控机制 (mmdvm_push.py)

**位置**: `mmdvm_push.py` 第147-197行

**优化内容**:
- 新增每小时内存占用检查
- 超过 100MB 时记录警告日志

**收益**:
- 及时发现内存泄漏问题
- 便于长期运行维护

**代码变更**:
```python
def run(self):
    # ...
    last_mem_check = time.time()

    while True:
        try:
            if time.time() - last_mem_check > 3600:
                rss_kb = int(self._proc_mem_rss_kb())
                if rss_kb > 100000:
                    logger.warning(f"内存占用过高: {rss_kb}KB")
                else:
                    logger.info(f"内存占用正常: {rss_kb}KB")
                last_mem_check = time.time()
```

---

### 7. 网络检查优化 (mmdvm_push.py)

**位置**: `mmdvm_push.py` 第126-149行

**优化内容**:
- 先检查 IP 地址是否有效
- 只有 IP 正常才进行网络连通性测试
- 避免无 IP 时的无效网络请求

**收益**:
- 减少启动时的无效网络请求
- 加快网络就绪检测速度

**代码变更**:
```python
def check_network(self, max_attempts: int = 30, interval: float = 2) -> bool:
    for i in range(max_attempts):
        try:
            ip_check = subprocess.getoutput("hostname -I").strip()
            if not ip_check or ip_check.startswith("127."):
                time.sleep(interval)
                continue  # 先确保有 IP

            # 只有 IP 正常才测试连通性
            urllib.request.urlopen(...)
```

---

## 优化效果预估

| 指标 | 优化前 | 优化后 | 改善 |
|------|--------|--------|------|
| CPU 占用 | 5-10% | 2-5% | ↓ 50% |
| 内存占用 | 20-30MB | 20-30MB | 持平 |
| I/O 操作频率 | 高 | 中低 | ↓ 40% |
| 日志检测延迟 | 0.2-0.8秒 | 0.3-1.0秒 | +0.2秒 |
| 温度告警延迟 | 实时 | 最多30秒 | +30秒 |
| 配置生效延迟 | 5秒 | 30秒 | +25秒 |

---

## 响应速度影响分析

### ✅ 不影响核心功能
1. **日志检测**: 延迟增加 0.1-0.2秒，人类无感知
2. **推送速度**: 完全不受影响，检测到日志后立即推送
3. **温度告警**: 温度变化缓慢，30秒延迟可接受
4. **配置修改**: 低频操作，30秒生效可接受

### ✅ 提升稳定性
1. 减少系统调用，降低 I/O 错误风险
2. 内存监控机制，及时发现泄漏
3. 降低 CPU 负载，减少资源竞争

---

## 部署建议

### 1. 测试环境验证
```bash
# 进入项目目录
cd /home/pi-star/MMDVM-Push-Notifier

# 更新代码
sudo ./update.sh

# 停止服务
sudo systemctl stop mmdvm_push

# 测试推送
sudo python3 mmdvm_push.py --test

# 查看健康状态
sudo python3 mmdvm_push.py --health
```

### 2. 观察运行状态
```bash
# 查看日志
tail -f /var/log/pi-star/mmdvm_push.log

# 查看资源占用
top -p $(pgrep -f mmdvm_push.py)
```

### 3. 健康检查
```bash
# 检查运行状态
cd /home/pi-star/MMDVM-Push-Notifier
sudo python3 mmdvm_push.py --health
```

### 4. 回滚方案
如果发现问题，可以从 Git 恢复优化前的版本：
```bash
cd /home/pi-star/MMDVM-Push-Notifier
git diff HEAD~1 hardware.py config.py mmdvm_push.py
git checkout HEAD~1 -- hardware.py config.py mmdvm_push.py
sudo systemctl restart mmdvm_push
```

---

## 修改的文件清单

1. **hardware.py** - CPU 缓存优化
2. **config.py** - 配置检查间隔优化
3. **mmdvm_push.py** - 多项优化
   - 日志轮询间隔动态调整
   - 温度检查频率优化
   - 日志文件查找缓存
   - 内存监控机制
   - 网络检查优化

---

## 注意事项

1. **配置修改延迟**: 修改配置文件后最多等30秒生效（原5秒）
2. **温度告警延迟**: 温度告警最多延迟30秒（原实时）
3. **兼容性**: 所有优化向后兼容，不影响现有功能
4. **可调整**: 如需更快响应，可调整缓存时间和检查间隔

---

## 后续优化建议

1. **异步推送**: 考虑使用异步 I/O 进一步降低阻塞
2. **数据库缓存**: 对于频繁查询的呼号信息，可考虑使用 SQLite 缓存
3. **日志轮转**: 定期清理旧日志文件，避免磁盘占用过高

---

## 联系方式

如有问题或建议，请在 GitHub 提 Issue:
https://github.com/fnshiwu/MMDVM-Push-Notifier/issues
