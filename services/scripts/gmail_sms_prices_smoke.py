"""联网 smoke：用 sms.db 里已配置的密钥，实跑三家 provider 的 get_prices("go")，
打印每家国家数 + 最便宜的前 3 个国家。验证 Task 1/2 的查价链路对真实 API 通。
跑法：cd services && python scripts/gmail_sms_prices_smoke.py
"""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sms_service.providers.base import ProviderRegistry
import sms_service.providers.sms_cloud  # noqa: F401  触发 @register
import sms_service.providers.hero_sms  # noqa: F401
import sms_service.providers.sms_bower  # noqa: F401


def _cfg(name: str):
    db = Path(__file__).resolve().parents[1] / "sms.db"
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            "SELECT config FROM sms_platform_configs WHERE provider_name=?", (name,)
        ).fetchone()
    finally:
        con.close()
    if not row:
        return None
    raw = row[0]
    return json.loads(raw) if isinstance(raw, str) else raw


async def main():
    for name in ("hero_sms", "sms_bower", "sms_cloud"):
        cfg = _cfg(name)
        if not cfg:
            print(f"{name}: 未配置（sms.db 无密钥）")
            continue
        try:
            rows = await ProviderRegistry.get(name, cfg).get_prices("go")
            cheapest = [(r["country"], r.get("country_name", ""), r["cost"], r["count"]) for r in rows[:3]]
            print(f"{name}: {len(rows)} 国, 最便宜3: {cheapest}")
        except Exception as e:
            print(f"{name}: ERR {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
