# Gmail 混合注册优化（并发 + 稳定性）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `register_gmail_hybrid.py` 支持 5-10 个窗口并发注册，并修复代理故障/页面卡住等稳定性问题。

**Architecture:** 在现有 `register_gmail_hybrid.py` 上原地改造。`run()` 改为接受 `worker_id` 参数的独立 worker，`main()` 改用 `asyncio.gather` + `Semaphore` 并发调度。稳定性改进分散在各函数内部（重试循环、早退条件、超时兜底）。

**Tech Stack:** Python 3.13, asyncio, Playwright CDP, ixBrowser API

---

### Task 1: 创建浏览器窗口重试

**Files:**
- Modify: `register_gmail_hybrid.py` — `run()` 函数内 `create_browser + open_browser` 段

现有问题：`find_working_proxy` 通过 requests 校验代理，但 ixBrowser 的 `open_profile` 有自己更严的代理检测，偶尔报 "Proxy detection failed: socket hang up"。

- [ ] **Step 1: 把 create+open 包在重试循环里（最多 3 次，每次换 sid）**

在 `run()` 里找到：
```python
pid = bb.create_browser(name="gmail_hybrid", proxy_str=proxy)
info = bb.open_browser(pid)
```

替换为：

```python
for _browser_try in range(3):
    try:
        proxy = find_working_proxy(proxy_base[0]) if proxy_base else None
        if proxy_base and not proxy:
            log(f"[W{worker_id}] 代理不可用，重试...", "WARN")
            continue
        pid = bb.create_browser(name=f"gmail_{worker_id}", proxy_str=proxy)
        info = bb.open_browser(pid)
        break
    except Exception as e:
        log(f"[W{worker_id}] 创建窗口失败({_browser_try+1}/3): {e}", "WARN")
        if pid:
            try: bb.delete_browser(pid)
            except Exception: pass
            pid = None
        await asyncio.sleep(2)
else:
    log(f"[W{worker_id}] 3次创建窗口都失败，放弃", "ERR")
    return None
```

- [ ] **Step 2: 给 `run()` 加 `worker_id` 参数**

```python
async def run(args, worker_id=0):
```

同时把所有 `log(` 调用加前缀 `[W{worker_id}]`（搜索替换 `log(f"[` 为 `log(f"[W{worker_id}][`），方便并发时区分日志。简化做法：在函数开头定义局部 log wrapper：

```python
async def run(args, worker_id=0):
    prefix = f"W{worker_id}"
    def wlog(msg, level="INFO"):
        log(f"[{prefix}] {msg}", level)
```

然后函数内用 `wlog` 替代 `log`。

- [ ] **Step 3: 验证——单 worker 跑一次确认重试逻辑不影响正常流程**

```bash
python -c "import asyncio; from register_gmail_hybrid import run; import argparse; a=argparse.Namespace(auto_sms=False,manual=True,wait=30,delete_window=True); asyncio.run(run(a, worker_id=1))"
```

- [ ] **Step 4: Commit**

```bash
git add register_gmail_hybrid.py
git commit -m "feat: add browser creation retry + worker_id logging prefix"
```

---

### Task 2: drive_to_phone 每步重试

**Files:**
- Modify: `register_gmail_hybrid.py` — `drive_to_phone()` 函数

现有问题：代理慢时页面加载超时，fill_first 等不到输入框，后续步骤全部跳过。

- [ ] **Step 1: 把每个步骤（姓名/生日/用户名/密码）包在重试循环里**

改 `drive_to_phone`，以生日步为例（最容易卡的步骤）：

```python
# ---- 生日性别 ----
for _bd_try in range(3):
    if await fill_first(page, ['input#day', 'input[name=day]'], str(day), 20000):
        await fill_first(page, ['input#year', 'input[name=year]'], str(year), 4000)
        try:
            await page.click('#month', timeout=3000)
            await asyncio.sleep(0.6)
            await page.get_by_role('option', name=f'{month} 月', exact=True).click(timeout=3000)
        except Exception:
            pass
        await asyncio.sleep(0.4)
        try:
            await page.click('#gender', timeout=2500)
            await asyncio.sleep(0.6)
            await page.get_by_role('option', name='男', exact=True).click(timeout=3000)
        except Exception:
            pass
        await asyncio.sleep(0.4)
        await click_next(page)
        log("[browser] 生日已提交")
        await wait_url(page, "username", 25)
        break
    else:
        log(f"[browser] 生日填充失败({_bd_try+1}/3)，刷新重试", "WARN")
        await page.reload(wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
```

对姓名/密码步也加同样的重试模式（姓名步失败→刷新→重填姓名；密码步失败→刷新→从密码页开始重试）。

用户名步已有 4 次重试（换用户名），保持不变。

- [ ] **Step 2: Commit**

```bash
git add register_gmail_hybrid.py
git commit -m "feat: add per-step retry with page reload in drive_to_phone"
```

---

### Task 3: 手机号连续被拒早退

**Files:**
- Modify: `register_gmail_hybrid.py` — `browser_phone_and_finalize()` 内换号循环

现有问题：IP 被限频时 15 个号全试完才放弃，浪费 ~2 分钟。

- [ ] **Step 1: 加连续拒绝计数，达到 5 个连续拒绝就早退**

在 `browser_phone_and_finalize` 的换号循环开头加：

```python
consecutive_reject = 0
```

在号码被拒的分支里：

```python
else:
    consecutive_reject += 1
    if consecutive_reject >= 5:
        log("[sms] 连续5个号被拒(IP可能被限频)，提前放弃", "WARN")
        try: sms.release(pkey)
        except Exception: pass
        break
    # ... 原有的释放和继续逻辑
```

在号码被接受时重置：

```python
if await is_visible(page, "input#code, input[name=code]", 3):
    consecutive_reject = 0  # 被接受，重置计数
```

- [ ] **Step 2: 把 `max_tries` 默认值从 15 降到 10**

```python
max_tries = int(os.environ.get("SMS_MAX_TRIES", "10"))
```

- [ ] **Step 3: Commit**

```bash
git add register_gmail_hybrid.py
git commit -m "feat: early exit after 5 consecutive phone rejections"
```

---

### Task 4: unknownerror 处理简化

**Files:**
- Modify: `register_gmail_hybrid.py` — `browser_phone_and_finalize()` 的收尾段

现有问题：unknownerror 后的重试逻辑复杂（点下一步→可能回条款页→再点我同意→再等），有时反而把 session 搞乱。实际上 unknownerror 时账号已建成（SMTP 确认），不需要重试。

- [ ] **Step 1: 删除 unknownerror 重试块，简化为纯 SMTP 验证**

替换从 `# unknownerror 可重试` 到 `final_url = page.url` 的整段代码为：

```python
    # unknownerror 是结构性的（缺 DroidGuard），但账号已建成。直接 SMTP 验证。
    final_url = page.url
    acct_email = email or f"{profile.get('username','?')}@gmail.com"
    if "unknownerror" in final_url:
        log("[finalize] unknownerror（正常，缺 DroidGuard），SMTP 验证账号...")
    done = smtp_verify(acct_email)
    if done:
        log(f"[finalize] SMTP 确认账号存在: {acct_email}", "OK")
    elif "unknownerror" not in final_url and "signup" not in final_url:
        done = True
    else:
        log(f"[finalize] 账号未建成(SMTP 550)，终止页: {final_url[:70]}", "WARN")
```

- [ ] **Step 2: Commit**

```bash
git add register_gmail_hybrid.py
git commit -m "fix: simplify unknownerror handling - just SMTP verify, no retry"
```

---

### Task 5: relogin 超时兜底

**Files:**
- Modify: `register_gmail_hybrid.py` — `_relogin_same_window()` 函数

现有问题：passkey/speedbump 跳过循环可能无限等（5 轮 × 3 秒 = 15 秒，有时更久）。

- [ ] **Step 1: 给整个 relogin 加 30 秒总超时**

```python
async def _relogin_same_window(page, email, password):
    log("[relogin] 在同窗口重新登录...")
    try:
        await asyncio.wait_for(_do_relogin(page, email, password), timeout=45)
    except asyncio.TimeoutError:
        log("[relogin] 超时(45s)，跳过（账号已建成，不影响）", "WARN")
    except Exception as e:
        log(f"[relogin] 异常: {e}", "WARN")
```

把原有的 relogin 逻辑体搬到 `_do_relogin` 里（原封不动）。

- [ ] **Step 2: 跳过中间页只尝试 3 次（不是 5 次），且不匹配 `button[jsname="LgbsSe"]`（避免误点）**

```python
for _ in range(3):
    skipped = False
    for sel in ['button:has-text("Not now")', 'button:has-text("暂不")',
                'button:has-text("跳过")', 'button:has-text("Skip")']:
        # ... 不变
```

- [ ] **Step 3: Commit**

```bash
git add register_gmail_hybrid.py
git commit -m "fix: add 45s timeout to relogin, reduce skip attempts to 3"
```

---

### Task 6: 并发架构——main() 改造

**Files:**
- Modify: `register_gmail_hybrid.py` — `main()` 函数

- [ ] **Step 1: 添加 `--parallel` 参数**

```python
ap.add_argument("--parallel", type=int, default=1, help="并发窗口数(默认1)")
```

- [ ] **Step 2: 改 main() 为 asyncio 并发调度**

```python
def main():
    ap = argparse.ArgumentParser(description="Gmail 混合注册(浏览器铸BotGuard+HTTP手机验证)")
    ap.add_argument("--auto-sms", action="store_true", help="自动接码完成手机验证")
    ap.add_argument("--manual", action="store_true", help="浏览器里全手动填，脚本只接管手机步")
    ap.add_argument("--wait", type=int, default=240, help="等待到手机页的最大秒数")
    ap.add_argument("--count", type=int, default=1, help="批量注册个数")
    ap.add_argument("--parallel", type=int, default=1, help="并发窗口数(默认1)")
    ap.add_argument("--delete-window", action="store_true", help="注册后删除窗口(默认保留)")
    args = ap.parse_args()

    asyncio.run(_main_async(args))


async def _main_async(args):
    sem = asyncio.Semaphore(args.parallel)
    results = []
    save_lock = asyncio.Lock()  # 保护凭据文件并发写入

    async def worker(i):
        async with sem:
            log("=" * 50)
            log(f"### 第 {i}/{args.count} 个账号 (并发槽 {sem._value} 空闲) ###")
            log("=" * 50)
            try:
                return await run(args, worker_id=i, save_lock=save_lock)
            except Exception as e:
                log(f"[W{i}] 异常: {e}", "ERR")
                return None

    tasks = [worker(i) for i in range(1, args.count + 1)]
    results = await asyncio.gather(*tasks)

    ok = sum(1 for r in results if r and r.get("email"))
    log(f"批量完成: 成功 {ok}/{args.count}，结果见 accounts_gmail.txt", "OK")
    return 0 if ok else 1
```

- [ ] **Step 3: 给 `run()` 加 `save_lock` 参数，`save_account()` 改为异步安全写入**

```python
async def run(args, worker_id=0, save_lock=None):
    # ... 在 save_account 调用处传 lock:
    # save_account(acct, lock=save_lock)
```

```python
def save_account(acct, lock=None):
    import json as _json
    base = os.path.dirname(os.path.abspath(__file__))
    pid = str(acct.get("profile_id", ""))
    line = "----".join([acct["email"], acct["password"], acct["phone"], acct["name"], acct["birthday"], pid])
    path = os.path.join(base, "accounts_gmail.txt")
    # 并发安全：用文件追加模式（OS 级原子），不需要 asyncio lock
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        log(f"[save] 凭据 → {path} (profile_id={pid})")
    except Exception as e:
        log(f"[save] 写入失败: {e}", "WARN")
```

实际上文件追加（`"a"` 模式）在 OS 层面对于单行写入是原子的，所以 `save_lock` 不是必需的——但保留参数以备扩展。

- [ ] **Step 4: 删除旧的 `main()` 里的串行 for 循环**

确认旧代码已被完全替换。

- [ ] **Step 5: 验证——`--count 2 --parallel 2` 跑一次**

```bash
SMS_HERO_FIXED_PRICE=true python register_gmail_hybrid.py --auto-sms --count 2 --parallel 2 --wait 220
```

预期：两个窗口同时打开，各自独立注册。

- [ ] **Step 6: Commit**

```bash
git add register_gmail_hybrid.py
git commit -m "feat: add --parallel N concurrent registration with asyncio.Semaphore"
```

---

### Task 7: 清理死代码

**Files:**
- Modify: `register_gmail_hybrid.py`

- [ ] **Step 1: 删除不再使用的函数**

以下函数在全浏览器方案后已不再被调用：
- `extract_session()` — 仅在 HTTP 接管时使用
- `_login_new_window()` — 第二窗口登录，已被 `_relogin_same_window` 替代
- `_login_and_export_cookies()` — 同上

搜索确认无引用后删除。

- [ ] **Step 2: 删除 `import requests`（如果不再使用）**

`requests` 仅在 `http_session_from_browser` 中使用，该函数已删除。但 `find_working_proxy` 还用 `requests`，所以**保留**。

- [ ] **Step 3: Commit**

```bash
git add register_gmail_hybrid.py
git commit -m "chore: remove dead code (extract_session, _login_new_window, _login_and_export_cookies)"
```

---

## 实施顺序

```
Task 1 (窗口重试 + worker_id)
  → Task 2 (drive_to_phone 重试)
  → Task 3 (手机号早退)
  → Task 4 (unknownerror 简化)
  → Task 5 (relogin 超时)
  → Task 6 (并发架构)
  → Task 7 (清理死代码)
```

Task 1-5 是稳定性（互相独立），Task 6 依赖 Task 1（worker_id），Task 7 最后做。
