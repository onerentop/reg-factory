# 里程碑2b：Outlook 原生化（根抽取 + flow 改写）实施计划 — GATED 待干净/移动 IP

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。Steps 用 `- [ ]`。
> **⚠️ GATE：** Task 1-2 改动**在产的 `register_outlook`**，正确性只能靠真实注册实跑确认；当前 1024proxy BE 池已烧。**拿到干净/移动 IP 前不要执行 Task 1-2 的合并**——可先写好分支、Task 6 实跑通过再合。Task 4（能力）不碰根，可随时做。

**Goal:** 把 `register_outlook` 的表单/验证码内联逻辑安全抽成可调用函数（行为不变、根 loop 照常出号），落地 `PerimeterXHoldSolver` 能力，并把 `flows/outlook.py` 改成用 `IxBrowserService.session()` CM 包的 native Step。

**Architecture:** 纯重构抽取（register_outlook 变薄编排）→ 能力包抽出的函数 → flow 覆写 `run()` 在浏览器会话 CM 内跑 native 步骤。根与 worker 共用一份抽出的源。

**Tech Stack:** Python 3.13；根 `register_outlook_standalone.py`；services 测试 `cd services && python -m pytest ...`（pythonpath=["."], asyncio_mode=auto）；根 tests `pytest tests/...`。

**前置（M2a 已完成）：** `GraphTokenExtractor`、`IxBrowserService`(`session()` CM)、`default_outlook_bundle()` 已在 `services/worker/capabilities/`。

---

## 抽取边界（实测行号，register_outlook 在 register_outlook_standalone.py 623-1497）

| 阶段 | 行范围 | 抽成 | 失败退出点(→`return False`) | 成功 |
|---|---|---|---|---|
| Step 1-5 表单 | ~700–1099（`# Step 1: Enter email` 起，至 `# Step 6` 前） | `_fill_signup_form(page, context, idx=0, tag="") -> bool` | 该段内所有 `return None, None` | 穿透到末尾 → `return True` |
| Step 6 验证码 | 1100–1471（`# Step 6: CAPTCHA handling` 起，至 `if not verify_registered_outlook` 前） | `_solve_signup_captcha(page, context, idx=0, tag="") -> bool` | 1174 / 1436 / 1441 / 1456 → `return False` | 验证码通过、循环自然退出 → `return True` |

> 1473 `verify_registered_outlook` + 1480 `extract_graph_token` 在 captcha 之外，**留在 register_outlook**。`email`/`password` 是 Step1-5 设的局部变量，captcha 不产出它们。`max_press`/`human_press`/`_hp_announced` 等 Step6 局部状态随块一起搬进 `_solve_signup_captcha`（在函数内重新从 env 读取/初始化）。

---

## Task 1: 抽取 `_fill_signup_form`（改根，GATED）

**Files:** Modify `register_outlook_standalone.py`

- [ ] **Step 1: 抽取**。把 `register_outlook` 内 Step 1-5 块（`# Step 1: Enter email` 至 `# Step 6` 前一行）整体移到一个新顶层函数 `async def _fill_signup_form(page, context, idx=0, tag=""):`，紧挨 `register_outlook` 定义之前。块内：① 所有 `return None, None` 改 `return False`；② 末尾追加 `return True`；③ 块首若引用 `tag = f"[#{idx}]"` 已由参数提供则删重复赋值（保留一处）。
- [ ] **Step 2: 改 call site**。在 `register_outlook` 原 Step 1-5 位置替换为：
```python
        if not await _fill_signup_form(page, context, idx, tag):
            return None, None
```
- [ ] **Step 3: 静态验证**：
  - `python -c "import ast; ast.parse(open('register_outlook_standalone.py',encoding='utf-8').read()); print('OK')"` → OK
  - `python -c "import register_outlook_standalone as r; assert callable(r._fill_signup_form) and callable(r.register_outlook)"`
  - `git diff` 人工审：`_fill_signup_form` 函数体 == 原 Step1-5 块逐行一致（仅 `return None,None`→`return False` + 末尾 `return True`）；register_outlook 仅多一处调用、其余不变。
- [ ] **Step 4: 提交**（**不合主线，留分支待 Task 6 实跑**）：
```bash
git add register_outlook_standalone.py
git commit -m "refactor(outlook): 抽取 _fill_signup_form(纯重构,行为不变) [GATED 待实跑]"
```

---

## Task 2: 抽取 `_solve_signup_captcha`（改根，GATED）

**Files:** Modify `register_outlook_standalone.py`

- [ ] **Step 1: 抽取**。把 Step 6 块（行 1100 `# Step 6: CAPTCHA handling` 至 1471，即 `if not verify_registered_outlook` 前）整体移到新顶层函数 `async def _solve_signup_captcha(page, context, idx=0, tag=""):`（紧挨 register_outlook 前）。块内：① `return None, None`（1174/1436/1441/1456 对应位置）改 `return False`；② 验证码通过后原本"穿透到 verify"的路径改为 `return True`（即 Step 6 块所有正常结束路径 return True）；③ Step6 局部状态（`press_count`/`no_btn_rounds`/`max_press`/`human_press`/`_hp_announced` 等）在函数内初始化/从 env 读，与原块一致。
- [ ] **Step 2: 改 call site**。在 register_outlook 原 Step 6 位置替换为：
```python
        if not await _solve_signup_captcha(page, context, idx, tag):
            return None, None
```
（其后保留原有 `verify_registered_outlook` + `extract_graph_token` 逻辑不变。）
- [ ] **Step 3: 静态验证**：ast.parse OK；`r._solve_signup_captcha` callable；`git diff` 人工审函数体 == 原 Step6 块逐行一致（仅退出转换）。
- [ ] **Step 4: 提交**（不合主线，留分支）：
```bash
git add register_outlook_standalone.py
git commit -m "refactor(outlook): 抽取 _solve_signup_captcha(纯重构,行为不变) [GATED 待实跑]"
```

---

## Task 3: register_outlook 薄编排确认（改根，GATED）

**Files:** Modify `register_outlook_standalone.py`（若 Task1-2 后 register_outlook 仍有可下沉的内联，确保骨架为）：
```
navigate(referer) → _warm_session → _fill_signup_form → _solve_signup_captcha → verify_registered_outlook → extract_graph_token → return (email,password,graph)
```
- [ ] **Step 1**：核对 register_outlook 主体仅剩上述编排 + 各 call-site 的 `if not ...: return None,None`；无遗留的 Step1-6 内联。
- [ ] **Step 2: 静态验证** ast.parse + import。
- [ ] **Step 3: 提交**（不合主线）：`refactor(outlook): register_outlook 薄编排确认 [GATED]`

---

## Task 4: `PerimeterXHoldSolver` 能力 + 接入 bundle（不碰根，可随时做）

**Files:** Create `services/worker/capabilities/captcha/__init__.py`、`services/worker/capabilities/captcha/perimeterx.py`；Modify `services/worker/capabilities/outlook_bundle.py`；Test `services/tests/worker/test_perimeterx_solver.py`、扩 `test_outlook_bundle.py`

- [ ] **Step 1: 失败测试** `test_perimeterx_solver.py`（monkeypatch 根 `_solve_signup_captcha`）：
```python
import asyncio, sys, types
from worker.capabilities.captcha.perimeterx import PerimeterXHoldSolver
from worker.capabilities.interfaces import CaptchaService

def test_is_captcha_service_kind_perimeterx():
    s = PerimeterXHoldSolver()
    assert isinstance(s, CaptchaService) and s.kind == "perimeterx"

def test_solve_wraps_root(monkeypatch):
    captured = {}
    async def fake(page, context, idx=0, tag=""):
        captured["args"] = (page, context); return True
    root = types.ModuleType("register_outlook_standalone"); root._solve_signup_captcha = fake
    monkeypatch.setitem(sys.modules, "register_outlook_standalone", root)
    class P: context = "C"
    ok = asyncio.run(PerimeterXHoldSolver().solve(P(), {"idx": 3}))
    assert ok is True and captured["args"][1] == "C"
```
- [ ] **Step 2: 失败确认** `cd services && python -m pytest tests/worker/test_perimeterx_solver.py -v` → ModuleNotFoundError
- [ ] **Step 3: 实现** `services/worker/capabilities/captcha/perimeterx.py`：
```python
"""PerimeterXHoldSolver：包根 _solve_signup_captcha(长按+Arkose兜底)，原生 captcha 能力。
kind='perimeterx'(Outlook 主验证码=PerimeterX 长按)。不改根；惰性 import。"""
from worker.capabilities.interfaces import CaptchaService


class PerimeterXHoldSolver(CaptchaService):
    kind = "perimeterx"

    async def solve(self, page, context: dict) -> bool:
        from register_outlook_standalone import _solve_signup_captcha
        idx = (context or {}).get("idx", 0)
        return await _solve_signup_captcha(page, page.context, idx)
```
  `captcha/__init__.py`：`from worker.capabilities.captcha.perimeterx import PerimeterXHoldSolver`。
  改 `outlook_bundle.py`：建 `CaptchaResolver` 注册 `PerimeterXHoldSolver()`，塞进 `ServiceBundle(captcha=resolver, ...)`；扩 `test_outlook_bundle.py` 断言 `b.captcha is not None` 且能 `solve("perimeterx", ...)`（用 monkeypatch）。
- [ ] **Step 4: 通过 + 全 worker 套件绿**。
- [ ] **Step 5: 提交** `feat(worker): PerimeterXHoldSolver 能力 + 接入 default_outlook_bundle`。
  > 注：本能力依赖根 `_solve_signup_captcha`（Task 2 产出）。可在 Task 2 分支上做，或先写测试用 monkeypatch（不依赖真实根函数存在即可跑过单测）。

---

## Task 5: `flows/outlook.py` 改 native Step（CM 包，改 worker flow，GATED 实跑确认）

**Files:** Modify `services/worker/flows/outlook.py`；Test 扩 `test_outlook_flow.py`

- [ ] **Step 1**：`OutlookRegistrationFlow` 覆写 `run(context, from_step=1)`：用 `async with self._bundle().browser.session(proxy=context.get("proxy",""), idx=context.get("idx",0)) as sess:` 包住步骤执行；把 `sess.page`/`sess.context` 放进 context 供步骤用；步骤序列改 native：
  - `Generate credentials`(native，调 `generate_*`)
  - `Fill signup form`(native，`await _fill_signup_form(sess.page, sess.context, idx)`)
  - `Solve captcha`(native，`await self._bundle().captcha.solve("perimeterx", sess.page, {"idx": idx})`)
  - `Extract token`(native，`await self._bundle().tokens.extract(sess.page, EmailAccount(email,password))`)
  `_bundle()`：`self.services or default_outlook_bundle()`。
- [ ] **Step 2: fake-bundle 单测**：注入 fake bundle（fake browser.session CM / fake captcha / fake tokens），断言步骤按序调用、context 流转、navigate→warm 仍发生（或在 fill 内）；不碰真浏览器。
- [ ] **Step 3: 全 worker 套件绿。**
- [ ] **Step 4: 提交**（worker 改动可合，但**端到端未验证**，标注）：`refactor(worker): Outlook flow 改 native Step(CM包) [e2e 待 Task6]`

---

## Task 6: 实弹端到端验证（GATED — 必须干净/移动 IP）

**Files:** 无（验证 + 决定 Task1-3 分支是否合主线）

- [ ] **Step 1: 根 loop 不退**：干净 IP 下 `OUTLOOK_PROXIES=<clean> python outlook_reg_loop.py --count 2 --max-press 6`，确认仍出号（证明根抽取未破坏在产链路）。
- [ ] **Step 2: worker 原生路径出号**：触发 worker Outlook flow（经 Celery `register_outlook_single` 或直接 `await FlowRegistry.get("outlook").run({"proxy": clean, "idx": 0})`），确认原生步骤跑通、出 email+refresh_token。
- [ ] **Step 3**：两者皆通过 → 合并 Task1-3 根抽取分支到主线；否则按实跑报错回退/修复。
- [ ] **Step 4: 提交/合并** + 更新 spec 标记 M2b 完成、实跑验证通过。

---

## 验证策略小结
- Task 1-3（根抽取）：静态(ast/import) + 人工逐行 diff + **Task 6 实跑**（硬 gate）。
- Task 4（能力）：monkeypatch 单测，不依赖真实根/网络，可随时做。
- Task 5（flow）：fake-bundle 单测 + Task 6 实跑。
- 全程根 loop 对外行为/`tasks.py` 不变；worker 套件保持绿。
