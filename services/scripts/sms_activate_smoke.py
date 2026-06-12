"""SMS-Activate 系联网 smoke：用 sms.db 真实 key 打 hero + sms_bower 的
getBalance，验证 handler_api 协议对齐。手动运行(需联网+有效密钥)，不进 CI。
  cd f:/reg-factory/services && python scripts/sms_activate_smoke.py
"""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sms_service.providers.hero_sms import HeroSmsProvider  # noqa: E402
from sms_service.providers.sms_bower import SmsBowerProvider  # noqa: E402


def _load(provider_name: str) -> dict:
    db = Path(__file__).resolve().parents[1] / "sms.db"
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            "SELECT config FROM sms_platform_configs WHERE provider_name=?",
            (provider_name,),
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise SystemExit(f"{provider_name} 未在 sms.db 配置")
    return json.loads(row[0])


async def main() -> int:
    for name, cls in (("hero_sms", HeroSmsProvider), ("sms_bower", SmsBowerProvider)):
        bal = await cls(_load(name)).get_balance()
        print(f"OK: {name} balance = {bal}")
        assert isinstance(bal, float) and bal >= 0
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
