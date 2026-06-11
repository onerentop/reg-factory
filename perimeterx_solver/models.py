from dataclasses import dataclass, field, asdict


@dataclass
class CapturedRequest:
    url: str
    method: str
    req_body: str = ""
    resp_status: int = 0
    resp_body: str = ""
    req_headers: dict = field(default_factory=dict)
    resp_headers: dict = field(default_factory=dict)
    ts: float = 0.0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class CookieSnapshot:
    label: str
    ts: float
    cookies: dict = field(default_factory=dict)  # name -> value

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


_VALID_OUTCOMES = ("pass", "fail")


@dataclass
class Sample:
    run_id: str
    outcome: str  # "pass" | "fail"
    captured_at: float = 0.0
    requests: list = field(default_factory=list)        # list[CapturedRequest]
    cookie_snapshots: list = field(default_factory=list)  # list[CookieSnapshot]
    script_refs: list = field(default_factory=list)      # list[dict] {url, sha256, path}
    pointer_stream: list = field(default_factory=list)   # list[dict] {x,y,t,type}（仅真人采集）
    meta: dict = field(default_factory=dict)             # proxy/app_id/ua/...

    def __post_init__(self):
        if self.outcome not in _VALID_OUTCOMES:
            raise ValueError(f"outcome must be one of {_VALID_OUTCOMES}, got {self.outcome!r}")

    def to_dict(self):
        # asdict 递归序列化所有嵌套 dataclass（requests/cookie_snapshots），from_dict 负责还原。
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        s = cls(run_id=d["run_id"], outcome=d["outcome"], captured_at=d.get("captured_at", 0.0),
                script_refs=d.get("script_refs", []), pointer_stream=d.get("pointer_stream", []),
                meta=d.get("meta", {}))
        s.requests = [CapturedRequest.from_dict(x) for x in d.get("requests", [])]
        s.cookie_snapshots = [CookieSnapshot.from_dict(x) for x in d.get("cookie_snapshots", [])]
        return s
