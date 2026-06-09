from abc import ABC, abstractmethod
from typing import Any
import csv
import json
import io


class ExportStrategy(ABC):
    """导出策略接口。"""

    @abstractmethod
    def export(self, accounts: list[dict[str, Any]]) -> str:
        ...


class TxtExporter(ExportStrategy):
    def export(self, accounts: list[dict[str, Any]]) -> str:
        lines = []
        for a in accounts:
            tokens = a.get("tokens") or {}
            parts = [
                a.get("email", ""),
                a.get("password", ""),
                tokens.get("client_id", ""),
                tokens.get("refresh_token", ""),
            ]
            lines.append("----".join(parts))
        return "\n".join(lines)


class CsvExporter(ExportStrategy):
    def export(self, accounts: list[dict[str, Any]]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["email", "password", "platform", "status", "created_at"])
        for a in accounts:
            writer.writerow([
                a.get("email", ""),
                a.get("password", ""),
                a.get("platform", ""),
                a.get("status", ""),
                str(a.get("created_at", "")),
            ])
        return output.getvalue()


class JsonExporter(ExportStrategy):
    def export(self, accounts: list[dict[str, Any]]) -> str:
        return json.dumps(accounts, default=str, indent=2, ensure_ascii=False)


class ExporterFactory:
    """导出器工厂。根据格式名称返回对应策略。"""

    _strategies: dict[str, type[ExportStrategy]] = {
        "txt": TxtExporter,
        "csv": CsvExporter,
        "json": JsonExporter,
    }

    @classmethod
    def register(cls, name: str, strategy: type[ExportStrategy]) -> None:
        cls._strategies[name] = strategy

    @classmethod
    def get(cls, format_name: str) -> ExportStrategy:
        strategy_cls = cls._strategies.get(format_name)
        if strategy_cls is None:
            raise ValueError(f"Unknown export format: {format_name}")
        return strategy_cls()

    @classmethod
    def list_formats(cls) -> list[str]:
        return list(cls._strategies.keys())
