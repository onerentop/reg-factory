from dataclasses import dataclass

from .payload_tracer import PayloadTracer
from .crypto_locator import CryptoLocator


@dataclass
class InstrumentationResult:
    events: list
    traced: object
    crypto: object

    @property
    def event_count(self):
        return len(self.events)

    @classmethod
    def from_events(cls, events):
        return cls(events=events,
                   traced=PayloadTracer().trace(events),
                   crypto=CryptoLocator().locate(events))


class PxInstrumentedSession:
    """Facade：跑钉死 collector + 注入 hook + 汇聚 __pxhook 事件 → InstrumentationResult。

    活体驱动（连 CDP、addInitScript 注入 hook、exposeBinding 收事件）在 _instrument_perimeterx.py。
    这里只暴露 analyze() 纯装配，便于单测与复用。
    """

    def analyze(self, events) -> InstrumentationResult:
        return InstrumentationResult.from_events(events)
