# Gmail 混合注册方案优化设计：并发 + 稳定性

## 背景

`register_gmail_hybrid.py` 已验证可出号（~85秒/账号），但存在两个核心问题：
1. **稳定性不足**：代理瞬时故障、drive_to_phone 卡住、relogin 不稳定
2. **只能串行**：一次跑一个窗口，无法并发

## 稳定性优化

### 1. drive_to_phone 每步重试

当前问题：代理慢 → 页面加载超时 → fill_first 等不到输入框 → 后续步骤全部跳过。

修复：每步（姓名/生日/用户名/密码）失败后 **刷新页面重试**（最多 2 次），而不是直接跳过。伪代码：

```python
for attempt in range(3):
    if await fill_birthday(page): break
    await page.reload()
    await asyncio.sleep(3)
```

### 2. 创建窗口重试

当前问题：`find_working_proxy` 通过 requests 校验了代理，但 ixBrowser 自己的代理检测更严，偶尔 `open_profile` 报 "Proxy detection failed"。

修复：`create_browser + open_browser` 包在重试循环里（最多 3 次，每次换新 sid）。

### 3. unknownerror 处理简化

当前状态：d6fbce 的 unknownerror 是结构性的（缺 DroidGuard），无法消除，但 SMTP 确认账号已建成。

策略：**接受 unknownerror = 正常完成**。点完"我同意"后纯等 → SMTP 验证 → 成功即 relogin。不再尝试在 unknownerror 页面点"下一步"重试（这只是浪费时间且有时把 session 搞乱）。

### 4. relogin 稳定化

当前问题：passkey/speedbump 等中间页跳过不稳定。

修复：
- 固定跳过选择器序列 + 5 秒超时
- relogin 定义为 **best-effort**：成功=窗口已登录；失败=窗口未登录但账号已建成（不影响出号计数）
- 超时 30 秒未到 myaccount → 放弃 relogin，不阻塞

### 5. 手机号连续被拒早退

当前问题：IP 被限频时 15 个号全试完才放弃，浪费 ~2 分钟。

修复：浏览器方案里号码被拒 = `input#code` 不出现 → 连续 **5 个号都被拒**（不是 15 个）就提前放弃本轮，log "IP 可能被限频"。

## 并发架构

### 总体结构

```
register_gmail_hybrid.py --count 10 --parallel 5

main()
  ├─ 创建 asyncio.Semaphore(parallel)
  ├─ 创建 count 个 tasks
  └─ asyncio.gather(*tasks)

每个 task = register_one(semaphore)
  async with semaphore:
    1. find_working_proxy(独立 sid)
    2. create_browser(独立 profile, 含重试)
    3. drive_to_phone(含每步重试)
    4. browser_phone_and_finalize(含号码早退)
    5. _relogin_same_window(best-effort)
    6. close_browser(保留 profile)
```

### 关键设计

- **asyncio 并发**：Playwright 原生异步，单进程跑多个浏览器窗口，无多进程开销
- **Semaphore(N)**：限制同时运行的窗口数（默认 5），避免内存爆炸
- **独立 proxy sid**：每个 Worker 调用 `rotate_proxy_sid()` 获取独立出口 IP
- **共享 SMS**：hero-sms API 取号是原子操作，多 Worker 同时取不冲突
- **失败隔离**：每个 task 独立 try/except，一个失败不影响其他
- **凭据串行写入**：`save_account()` 加文件锁或 asyncio.Lock，避免并发写乱

### main() 改造

```python
async def main():
    args = parse_args()  # 新增 --parallel 参数
    sem = asyncio.Semaphore(args.parallel)
    
    async def worker(i):
        async with sem:
            return await run(args, worker_id=i)
    
    tasks = [worker(i) for i in range(args.count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    ok = sum(1 for r in results if isinstance(r, dict) and r.get("email"))
    log(f"批量完成: 成功 {ok}/{args.count}")
```

### 不变的部分

- 注册流程（GlifSetupAndroid + ixBrowser + Playwright CDP）
- SMS 接码（hero-sms fixedPrice $0.1024 泰国 52）
- 一号一窗口模型（profile_id 落盘）
- 凭据格式（accounts_gmail.txt: email----pw----phone----name----birthday----profile_id）

## 预期效果

| 指标 | 当前 | 优化后 |
|------|------|--------|
| 单账号耗时 | ~85s | ~85s（不变） |
| 吞吐量 | 1 个/85s | 5 个/85s（5x 并发） |
| 稳定性 | 偶发卡住/代理故障 | 自动重试，单 Worker 失败不影响全局 |
| 手动干预 | 无 | 无 |
