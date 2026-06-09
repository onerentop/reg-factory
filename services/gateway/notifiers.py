import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AlertNotifier(ABC):
    """告警通知渠道抽象基类。策略模式。"""

    @abstractmethod
    async def send(self, rule_name: str, message: str, details: dict[str, Any] | None = None) -> bool:
        ...


class WebNotifier(AlertNotifier):
    """页面内通知（通过 WebSocket 推送）。"""

    def __init__(self, ws_manager):
        self._ws_manager = ws_manager

    async def send(self, rule_name: str, message: str, details: dict[str, Any] | None = None) -> bool:
        await self._ws_manager.broadcast("alert", {
            "rule_name": rule_name, "message": message, "details": details,
        })
        return True


class WebhookNotifier(AlertNotifier):
    """Webhook 通知（POST JSON 到指定 URL）。"""

    def __init__(self, webhook_url: str):
        self._url = webhook_url

    async def send(self, rule_name: str, message: str, details: dict[str, Any] | None = None) -> bool:
        payload = {"rule_name": rule_name, "message": message, "details": details or {}}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self._url, json=payload)
                return resp.status_code < 400
        except Exception as e:
            logger.error(f"Webhook notification failed: {e}")
            return False


class EmailNotifier(AlertNotifier):
    """邮件通知（通过 SMTP 发送）。"""

    def __init__(self, smtp_host: str = "", smtp_port: int = 587, sender: str = "", password: str = "", recipients: list[str] | None = None):
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._sender = sender
        self._password = password
        self._recipients = recipients or []

    async def send(self, rule_name: str, message: str, details: dict[str, Any] | None = None) -> bool:
        if not self._smtp_host or not self._recipients:
            logger.warning("Email notification skipped: SMTP not configured")
            return False
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(f"Alert: {rule_name}\n\n{message}\n\nDetails: {json.dumps(details or {})}")
            msg["Subject"] = f"[RegFactory Alert] {rule_name}"
            msg["From"] = self._sender
            msg["To"] = ", ".join(self._recipients)
            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                server.login(self._sender, self._password)
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"Email notification failed: {e}")
            return False


class NotifierChain:
    """通知链。组合多个通知渠道，全部尝试发送。"""

    def __init__(self):
        self._notifiers: list[AlertNotifier] = []

    def add(self, notifier: AlertNotifier) -> "NotifierChain":
        self._notifiers.append(notifier)
        return self

    async def send_all(self, rule_name: str, message: str, details: dict[str, Any] | None = None) -> dict[str, bool]:
        results = {}
        for notifier in self._notifiers:
            name = notifier.__class__.__name__
            results[name] = await notifier.send(rule_name, message, details)
        return results
