"""浏览器输入辅助。从 common/browser.py 迁移 human_type + react_fill。"""

import asyncio
import random


class InputHelper:

    @staticmethod
    async def human_type(page, selector: str, text: str, delay_range: tuple = (0.05, 0.18)) -> None:
        el = page.locator(selector).first
        await el.click()
        for ch in text:
            await el.type(ch, delay=random.uniform(*delay_range) * 1000)
        await asyncio.sleep(random.uniform(0.2, 0.5))

    @staticmethod
    async def react_fill(page, selector: str, text: str, tries: int = 3, delay: int = 55, settle: float = 0.6) -> bool:
        el = page.locator(selector).first
        try:
            if await el.count() == 0:
                return False
        except Exception:
            return False

        async def _readback():
            try:
                return (await el.input_value()).strip()
            except Exception:
                return ""

        for i in range(tries):
            try:
                await el.click(timeout=4000)
                await el.press("Control+A", timeout=2000)
                await el.press("Delete", timeout=2000)
                await page.keyboard.type(text, delay=delay)
            except Exception:
                pass
            await asyncio.sleep(settle)
            if await _readback() == text:
                return True

            try:
                await el.evaluate(
                    """(node, v) => {
                        const proto = node.tagName === 'TEXTAREA'
                            ? window.HTMLTextAreaElement.prototype
                            : window.HTMLInputElement.prototype;
                        const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                        setter.call(node, v);
                        node.dispatchEvent(new Event('input', {bubbles: true}));
                        node.dispatchEvent(new Event('change', {bubbles: true}));
                    }""", text)
            except Exception:
                pass
            await asyncio.sleep(settle)
            if await _readback() == text:
                return True

        return False

    @staticmethod
    def react_fill_js(text: str) -> str:
        return f"""(node) => {{
            const proto = node.tagName === 'TEXTAREA'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(node, {repr(text)});
            node.dispatchEvent(new Event('input', {{bubbles: true}}));
            node.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}"""
