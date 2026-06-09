from typing import Any
from gateway.repository import AlertRuleRepository, AlertHistoryRepository
from gateway.schemas import AlertRuleRead
from gateway.websocket_hub import ws_manager


class AlertEngine:
    """告警引擎。评估规则并触发通知。"""

    def __init__(
        self,
        rule_repo: AlertRuleRepository,
        history_repo: AlertHistoryRepository,
    ):
        self._rule_repo = rule_repo
        self._history_repo = history_repo

    async def list_rules(self) -> list[AlertRuleRead]:
        rules = await self._rule_repo.get_enabled()
        return [AlertRuleRead(
            id=str(r.id), name=r.name, rule_type=r.rule_type,
            threshold=r.threshold, enabled=r.enabled,
            notify_channels=r.notify_channels,
        ) for r in rules]

    async def trigger_alert(self, rule_name: str, rule_type: str, message: str) -> None:
        await self._history_repo.create(
            rule_name=rule_name, rule_type=rule_type,
            message=message, resolved=False,
        )
        await ws_manager.broadcast("alert", {
            "rule_name": rule_name,
            "rule_type": rule_type,
            "message": message,
        })

    async def check_balance_alert(self, provider: str, balance: float, threshold: float) -> None:
        if balance < threshold:
            await self.trigger_alert(
                rule_name=f"sms_balance_{provider}",
                rule_type="sms_balance",
                message=f"SMS platform '{provider}' balance ${balance:.2f} below threshold ${threshold:.2f}",
            )
