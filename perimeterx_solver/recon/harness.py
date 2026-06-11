# perimeterx_solver/recon/harness.py
from ..corpus import SampleCorpus
from ..models import Sample


def outcome_from_cookies(cookies) -> str:
    return "pass" if any(c.get("name") == "_px3" for c in cookies) else "fail"


class ReconHarness:
    """侦查骨架（Template Method）。子类实现 _open_session/_drive_to_challenge/_collect/_close_session。"""

    def __init__(self, corpus: SampleCorpus, run_id: str, meta: dict):
        self.corpus = corpus
        self.run_id = run_id
        self.meta = meta or {}

    # --- 抽象步骤 ---
    def _open_session(self):
        raise NotImplementedError

    def _drive_to_challenge(self, session):
        raise NotImplementedError

    def _collect(self, session):
        """返回 (requests, cookie_snapshots, final_cookies, pointer_stream)。"""
        raise NotImplementedError

    def _close_session(self, session):
        raise NotImplementedError

    # --- 固定流程 ---
    def run(self) -> Sample:
        session = self._open_session()
        try:
            self._drive_to_challenge(session)
            requests, snaps, final_cookies, pointer = self._collect(session)
        finally:
            self._close_session(session)
        sample = Sample(run_id=self.run_id, outcome=outcome_from_cookies(final_cookies), meta=self.meta)
        sample.requests = requests
        sample.cookie_snapshots = snaps
        sample.pointer_stream = pointer
        self.corpus.save(sample)
        return sample
