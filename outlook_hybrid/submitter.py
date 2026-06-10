"""协议侧：装载凭证 → 立即 replay CreateAccount → 校验 → 抽 token。无浏览器。"""

from dataclasses import dataclass

import requests

from .cookies import playwright_cookies_to_requests
from .credential import MintedCredential
from .errors import SubmitRejected

CREATE_ACCOUNT_URL = "https://signup.live.com/API/CreateAccount?lic=1"


@dataclass
class RegistrationResult:
    success: bool
    email: str = ""
    password: str = ""
    refresh_token: str = ""
    mode_used: str = "hybrid"
    error: str = ""

    @property
    def has_token(self) -> bool:
        return bool(self.refresh_token)


class ProtocolSubmitter:
    """注入 token_extractor 与 verifier，便于测试与解耦。

    token_extractor(email, password, proxy) -> refresh_token(str)
    verifier(email, password, tag="") -> bool
    """

    def __init__(self, token_extractor, verifier):
        self._extract = token_extractor
        self._verify = verifier
        self._session_factory = requests.Session  # 测试可替换

    def submit(self, cred: MintedCredential) -> RegistrationResult:
        from register_outlook_standalone import _proxy_for_requests

        session = self._session_factory()
        session.headers.update({"User-Agent": cred.user_agent})
        playwright_cookies_to_requests(session.cookies, cred.cookies)

        headers = {
            "canary": cred.request_headers.get("canary", cred.canary),
            "hpgid": cred.request_headers.get("hpgid", ""),
            "scid": cred.request_headers.get("scid", "100118"),
            "Origin": "https://signup.live.com",
            "Referer": "https://signup.live.com/signup?lic=1",
            "Content-Type": "application/json",
        }
        proxies = _proxy_for_requests(cred.proxy)

        try:
            resp = session.post(CREATE_ACCOUNT_URL, json=cred.create_payload,
                                 headers=headers, proxies=proxies, timeout=30)
        except Exception:
            # 网络错误：窗口内重发一次
            resp = session.post(CREATE_ACCOUNT_URL, json=cred.create_payload,
                                headers=headers, proxies=proxies, timeout=30)

        body = resp.text or ""
        try:
            data = resp.json()
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                raise SubmitRejected(f"code={err.get('code')} data={str(err.get('data') or err.get('message'))[:120]}")
        except SubmitRejected:
            raise
        except Exception:
            pass

        if resp.status_code == 200 and "error" not in body.lower():
            email, password = cred.email, cred.password
            if not self._verify(email, password, tag="[hybrid]"):
                return RegistrationResult(success=False, email=email, password=password,
                                          mode_used="hybrid", error="verify failed")
            try:
                token = self._extract(email, password, cred.proxy) or ""
            except Exception:
                token = ""
            return RegistrationResult(success=True, email=email, password=password,
                                      refresh_token=token, mode_used="hybrid")

        raise SubmitRejected(f"unexpected status={resp.status_code} body={body[:120]}")
