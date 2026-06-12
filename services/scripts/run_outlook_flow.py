"""通过新架构运行 Outlook 注册全流程。

直接调用 step_engine 的 OutlookRegistrationFlow，不经过 Celery。
自动从 .env 加载代理配置。
"""

import asyncio
import sys
import os
import random
from datetime import datetime

# 确保 services/ 和项目根目录都在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 触发 .env 加载
try:
    import config  # noqa: F401
except Exception:
    pass

from worker.step_engine import FlowRegistry


def load_proxy() -> str:
    """从环境变量 OUTLOOK_PROXIES 加载代理，随机选一个。"""
    raw = os.environ.get("OUTLOOK_PROXIES", "")
    if not raw:
        return ""
    proxies = [p.strip() for p in raw.replace(",", "\n").splitlines() if p.strip() and not p.strip().startswith("#")]
    if not proxies:
        return ""
    selected = random.choice(proxies)
    print(f"  使用代理: {selected[:30]}...")
    return selected


async def main():
    print("=" * 60)
    print("RegFactory 新架构 — Outlook 注册全流程")
    print("=" * 60)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    proxy = load_proxy()
    if not proxy:
        print("⚠️  未配置代理 (OUTLOOK_PROXIES)，将不使用代理")
    print()

    flow = FlowRegistry.get("outlook")
    steps = flow.get_steps()
    print(f"流程: {flow.__class__.__name__}")
    print(f"步骤: {' → '.join(steps)}")
    print()

    context = {
        "idx": 0,
        "proxy": proxy,
    }

    results = await flow.run(context)

    print()
    print("=" * 60)
    print("执行结果:")
    print("=" * 60)
    for r in results:
        status = "✅" if r.success else "❌"
        print(f"  {status} [{r.step_number}] {r.name} ({r.duration_ms}ms)")
        if r.error:
            print(f"     错误: {r.error}")
        if r.data:
            for k, v in r.data.items():
                if k not in ("password",):
                    print(f"     {k}: {v}")

    print()
    all_success = all(r.success for r in results)
    if all_success:
        print("🎉 全部步骤成功!")
        print(f"   邮箱: {context.get('email', 'N/A')}")
        print(f"   密码: {context.get('password', 'N/A')}")
        print(f"   Token: {'有' if context.get('refresh_token') else '无'}")
    else:
        failed = next(r for r in results if not r.success)
        print(f"💥 在步骤 [{failed.step_number}] {failed.name} 失败")
        print(f"   错误: {failed.error}")

    return all_success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
