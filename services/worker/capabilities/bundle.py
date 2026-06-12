"""ServiceBundle：共享能力的依赖注入容器。本里程碑各平台仍走 bridge，故全字段可选。"""

from dataclasses import dataclass
from typing import Any

from worker.capabilities.interfaces import (
    BrowserService, ProxyService, CaptchaResolver,
    EmailPoolService, SmsService, TokenExtractor,
)


@dataclass
class ServiceBundle:
    browser: BrowserService | None = None
    proxy: ProxyService | None = None
    captcha: CaptchaResolver | None = None
    emails: EmailPoolService | None = None
    sms: SmsService | None = None
    tokens: TokenExtractor | None = None
    accounts: Any | None = None   # AccountRepository（现成于 account_service，后续注入）
