# -*- coding: utf-8 -*-
"""
scripts/verify_donut_provider.py — donut provider 端到端自检。

验证 DonutBrowserProvider 全链路：
  1. list_browsers 读现有 profile
  2. create_browser 建 proxy(可选) + profile
  3. open_browser run 开窗口拿 CDP
  4. 用 playwright connect_over_cdp 连上（若装了 playwright）
  5. close_browser kill
  6. delete_browser 删 profile

用法: python scripts/verify_donut_provider.py [--name test_xxx] [--proxy socks5://...]
"""

import os
import sys
import argparse

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.donut_provider import DonutBrowserProvider, DonutAPIError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="donut_verify")
    ap.add_argument("--proxy", default="")
    ap.add_argument("--skip-open", action="store_true", help="只测建/列/删，不 open（旧二进制付费墙下用）")
    args = ap.parse_args()

    p = DonutBrowserProvider()
    print(f"[1/6] provider 初始化 OK (base={p.base})")

    print(f"[2/6] list_browsers:")
    listing = p.list_browsers()
    for row in listing["data"]["list"][:5]:
        print(f"      #{row['id']} {row['name']}")

    pid = p.create_browser(name=args.name, proxy_str=args.proxy or None)
    print(f"[3/6] create_browser OK: {pid}")

    if args.skip_open:
        print("[4/6] (skip-open) 跳过 open/kill")
    else:
        try:
            data = p.open_browser(pid)
            print(f"[4/6] open_browser OK: {data}")
            # 尝试 CDP 连接
            try:
                from playwright.async_api import async_playwright
                import asyncio
                async def _probe():
                    async with async_playwright() as pw:
                        b = await pw.chromium.connect_over_cdp(data["http"])
                        print(f"      CDP 连接 OK, contexts={len(b.contexts)}")
                        await b.close()
                asyncio.run(_probe())
            except ImportError:
                print("      (playwright 未装，跳过 CDP 连接)")
        except DonutAPIError as e:
            print(f"[4/6] open_browser 失败: {e}")
            if e.status == 402:
                print("      → 付费墙 402。需要带 e2e 后门的 donut 构建。")
        finally:
            p.close_browser(pid)
            print("[5/6] close_browser done")

    p.delete_browser(pid)
    print("[6/6] delete_browser done")
    print("\n✅ 全流程跑完")


if __name__ == "__main__":
    main()
