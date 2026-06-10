import asyncio
import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright

from outlook_hybrid.minter import install_create_account_interceptor


def test_interceptor_captures_payload_and_aborts():
    asyncio.run(_run_capture_check())


async def _run_capture_check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 伪造签到页：导航到 signup.live.com 时返回一段会 fetch CreateAccount 的 HTML
        async def _serve_html(route):
            await route.fulfill(status=200, content_type="text/html", body="""
                <html><body><script>
                  window.__done = fetch('/API/CreateAccount?lic=1', {
                    method:'POST',
                    headers:{'Content-Type':'application/json','canary':'CANARY42','hpgid':'200225'},
                    body: JSON.stringify({MemberName:'u@outlook.com', Password:'Pw!1', HSol:'TOK99'})
                  }).then(r=>'ok').catch(e=>'aborted');
                </script></body></html>
            """)

        await page.route("https://signup.live.com/", _serve_html)
        fut = await install_create_account_interceptor(page)

        await page.goto("https://signup.live.com/", wait_until="domcontentloaded")
        cap = await asyncio.wait_for(fut, timeout=10)

        assert cap["payload"]["HSol"] == "TOK99"
        assert cap["payload"]["MemberName"] == "u@outlook.com"
        assert cap["headers"].get("canary") == "CANARY42"

        # fetch 应被 abort（页面脚本 catch 到 'aborted'）
        result = await page.evaluate("() => window.__done")
        assert result == "aborted"

        await browser.close()
