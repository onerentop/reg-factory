"""浏览器铸出的会话凭证。协议侧据此逐字 replay。"""

from dataclasses import dataclass, field


@dataclass
class MintedCredential:
    cookies: list[dict] = field(default_factory=list)   # context.cookies()，含 _px*
    canary: str = ""                                     # 请求头 apiCanary
    create_payload: dict = field(default_factory=dict)  # 截获的 CreateAccount JSON 体（含 HSol/MemberName/Password）
    request_headers: dict = field(default_factory=dict)  # canary/hpgid/scid/...
    user_agent: str = ""                                 # 必须与协议 Session 一致
    proxy: str = ""
    captured: bool = False

    @property
    def email(self) -> str:
        return self.create_payload.get("MemberName", "")

    @property
    def password(self) -> str:
        return self.create_payload.get("Password", "")

    @property
    def has_token(self) -> bool:
        return bool(self.create_payload.get("HSol"))
