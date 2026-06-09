from typing import Any


class AccountImporter:
    """历史数据导入器。支持 txt 和 json 格式。"""

    @staticmethod
    def parse_txt(content: str, platform: str) -> list[dict[str, Any]]:
        accounts = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("----")
            account = {
                "email": parts[0] if len(parts) > 0 else "",
                "password": parts[1] if len(parts) > 1 else "",
                "platform": platform,
                "tokens": {},
            }
            if len(parts) > 2 and parts[2]:
                account["tokens"]["refresh_token"] = parts[2]
            if len(parts) > 3 and parts[3]:
                account["tokens"]["client_id"] = parts[3]
            if account["email"]:
                accounts.append(account)
        return accounts

    @staticmethod
    def parse_json(content: str, platform: str) -> list[dict[str, Any]]:
        import json
        data = json.loads(content)
        if isinstance(data, list):
            for item in data:
                item.setdefault("platform", platform)
            return data
        return []

    @classmethod
    def parse(cls, content: str, format_name: str, platform: str) -> list[dict[str, Any]]:
        if format_name == "txt":
            return cls.parse_txt(content, platform)
        elif format_name == "json":
            return cls.parse_json(content, platform)
        else:
            raise ValueError(f"Unknown import format: {format_name}")
