# -*- coding: utf-8 -*-
"""Phase 0 验证：浏览器铸 HSol → 协议 replay 能否被 MS 接受。一次性脚本，验证后删除。
用法：python _spike_outlook_hybrid.py "<proxy_str>"
"""
import asyncio, json, sys, time
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import config  # noqa: 触发 .env
from common.browser_provider import get_browser_provider
from register_outlook_standalone import (
    register_outlook, _proxy_for_requests, verify_registered_outlook,
)


async def _drive_and_capture(proxy_str):
    """起浏览器跑 register_outlook，路由拦截 CreateAccount，截获 payload/headers/cookies/UA 后 abort。"""
    from playwright.async_api import async_playwright
    bb = get_browser_provider()
    profile_id = bb.create_browser(name="spike_outlook", proxy_str=proxy_str)
    info = bb.open_browser(profile_id)
    ws = info.get("ws", "")
    captured = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()

            fut = asyncio.get_event_loop().create_future()

            async def _intercept(route):
                req = route.request
                try:
                    body = json.loads(req.post_data or "{}")
                except Exception:
                    body = {}
                if body.get("HSol"):
                    if not fut.done():
                        fut.set_result({"payload": body, "headers": dict(req.headers)})
                    await route.abort()
                else:
                    # 无 HSol 的首次提交放行，让验证码挑战正常出现
                    await route.continue_()

            await page.route("**/API/CreateAccount*", _intercept)

            drive = asyncio.create_task(register_outlook(page, context, 0))
            try:
                cap = await asyncio.wait_for(asyncio.shield(fut), timeout=420)
            except asyncio.TimeoutError:
                drive.cancel()
                print("[spike] CreateAccount 未被触发/截获，超时")
                return None
            drive.cancel()
            try:
                await drive
            except asyncio.CancelledError:
                pass

            captured["payload"] = cap["payload"]
            captured["headers"] = cap["headers"]
            # UA 从截获的请求头取（页面可能已跳转，page.evaluate 会 context destroyed）
            captured["ua"] = cap["headers"].get("user-agent", "")
            try:
                captured["cookies"] = await context.cookies()
            except Exception:
                captured["cookies"] = []
    finally:
        try:
            bb.close_browser(profile_id); bb.delete_browser(profile_id)
        except Exception:
            pass
    return captured


def _replay(captured, proxy_str):
    """立即用截获的会话 replay CreateAccount。"""
    payload = captured["payload"]
    headers_in = captured["headers"]
    email = payload.get("MemberName", "")
    password = payload.get("Password", "")
    print(f"[spike] 截获 email={email} HSol={'有' if payload.get('HSol') else '无'} canary={'有' if headers_in.get('canary') else '无'}")

    s = requests.Session()
    s.headers.update({"User-Agent": captured["ua"]})
    for c in captured["cookies"]:
        dom = c.get("domain", "")
        s.cookies.set(c["name"], c["value"], domain=dom.lstrip("."), path=c.get("path", "/"))

    hdr = {
        "canary": headers_in.get("canary", ""),
        "hpgid": headers_in.get("hpgid", ""),
        "scid": headers_in.get("scid", "100118"),
        "Origin": "https://signup.live.com",
        "Referer": "https://signup.live.com/signup?lic=1",
        "Content-Type": "application/json",
    }
    r = s.post("https://signup.live.com/API/CreateAccount?lic=1",
               json=payload, headers=hdr,
               proxies=_proxy_for_requests(proxy_str), timeout=30)
    print(f"[spike] replay status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200 and "error" not in r.text.lower():
        ok = verify_registered_outlook(email, password, "[spike]")
        print(f"[spike] 校验登录: {'成功 ✅ 假设成立' if ok else '失败 ❌'}")
        return ok
    return False


async def _main():
    proxy_str = sys.argv[1] if len(sys.argv) > 1 else ""
    captured = await _drive_and_capture(proxy_str)
    if not captured:
        print("[spike] 结论：未能截获，检查浏览器/验证码")
        return
    ok = _replay(captured, proxy_str)
    print(f"\n[spike] === 最终结论：{'PASS — 按计划建完整混合' if ok else 'FAIL — 切换降级语义（见计划 Task 0 决策门）'} ===")


if __name__ == "__main__":
    asyncio.run(_main())
