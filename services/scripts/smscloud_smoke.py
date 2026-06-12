"""SMS Cloud 联网 smoke：用 sms.db 里真实 apiKey 打余额接口，验证协议对齐。
手动运行(需联网+有效密钥)，不进 CI。
  cd f:/reg-factory/services && python scripts/smscloud_smoke.py
"""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sms_service.providers.sms_cloud import SmsCloudProvider  # noqa: E402


def _load_config() -> dict:
    db = Path(__file__).resolve().parents[1] / "sms.db"
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            "SELECT config FROM sms_platform_configs WHERE provider_name='sms_cloud'"
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise SystemExit("sms_cloud 未在 sms.db 配置")
    return json.loads(row[0])


async def main() -> int:
    provider = SmsCloudProvider(_load_config())
    balance = await provider.get_balance()
    print(f"OK: sms_cloud balance = {balance}")
    assert isinstance(balance, float)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
