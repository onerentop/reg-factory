"""一次性修复：sms.db 里 sms_bower 的 base_url 旧值 https://smsbower.com/api
改成 SMS-Activate handler_api 端点，保留 api_key。幂等可重跑。
  cd f:/reg-factory/services && python scripts/fix_sms_bower_baseurl.py
"""
import json
import sqlite3
from pathlib import Path

CORRECT = "https://smsbower.com/stubs/handler_api.php"


def main() -> int:
    db = Path(__file__).resolve().parents[1] / "sms.db"
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            "SELECT config FROM sms_platform_configs WHERE provider_name='sms_bower'"
        ).fetchone()
        if not row:
            print("sms_bower 未在 sms.db 配置，跳过")
            return 0
        cfg = json.loads(row[0])
        old = cfg.get("base_url")
        cfg["base_url"] = CORRECT
        con.execute(
            "UPDATE sms_platform_configs SET config=? WHERE provider_name='sms_bower'",
            (json.dumps(cfg),),
        )
        con.commit()
        print(f"OK: sms_bower base_url {old!r} -> {CORRECT!r} (api_key 保留)")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
