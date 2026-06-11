# -*- coding: utf-8 -*-
"""统一的 Playwright 入口（隐身适配层）。

背景：PerimeterX / Cloudflare / DataDome 等通用反爬会检测 Playwright 客户端发出的
`Runtime.enable` CDP 命令——这是把"被自动化控制"暴露给页面脚本的头号泄漏点，且
**connect_over_cdp 接管已启动浏览器时同样发生**（补丁在客户端驱动层，与浏览器谁启动无关）。

`rebrowser-playwright` 是 Playwright 的 drop-in 补丁版：禁掉每个 frame 自动发的
`Runtime.enable`，改用未知 ID 手动建 context，从而堵掉该泄漏。本模块优先用它，缺失时
回退原版 playwright，**API 完全一致**，调用方无需感知。

用法（替换原 `from playwright.async_api import async_playwright`）：
    from common.stealth_playwright import async_playwright, USING_REBROWSER

环境变量 `REBROWSER_PATCHES_RUNTIME_FIX_MODE` 控制修复模式（默认 addBinding）：
    addBinding     —— 推荐：保留 main world 访问，支持 iframe/worker，目前无已知缺点
    alwaysIsolated —— 全部在 isolated context 执行，隐蔽性更强，但无法访问 main world 变量
    enableDisable  —— Runtime.enable 后立刻 disable（有极小时间窗泄漏风险）
    0              —— 关闭修复（等价于原版 playwright 行为）
"""

import os

# 在 import patch 版之前确保有默认 fix mode；不覆盖外部已设置的值。
os.environ.setdefault("REBROWSER_PATCHES_RUNTIME_FIX_MODE", "addBinding")

try:
    from rebrowser_playwright.async_api import async_playwright  # type: ignore  # noqa: F401
    USING_REBROWSER = True
except ImportError:  # 未安装则回退原版，功能不受影响（只是少了 Runtime.enable 隐身）
    from playwright.async_api import async_playwright  # type: ignore  # noqa: F401
    USING_REBROWSER = False

# 当前生效的 Runtime.enable 修复模式（便于调用方打印诊断）
RUNTIME_FIX_MODE = os.environ.get("REBROWSER_PATCHES_RUNTIME_FIX_MODE", "")


def stealth_banner() -> str:
    """一行诊断串，跑前打印用来确认隐身链路是否生效。"""
    if USING_REBROWSER:
        return f"[stealth] rebrowser-playwright 生效 (Runtime.enable fix={RUNTIME_FIX_MODE})"
    return "[stealth] 原版 playwright（未装 rebrowser-playwright，Runtime.enable 泄漏未修复）"
