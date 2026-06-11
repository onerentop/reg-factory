# tests/perimeterx_solver/test_harness.py
from perimeterx_solver.recon.harness import ReconHarness, outcome_from_cookies


def test_outcome_from_cookies():
    assert outcome_from_cookies([{"name": "_px3", "value": "t"}]) == "pass"
    assert outcome_from_cookies([{"name": "_pxhd", "value": "h"}]) == "fail"


def test_harness_template_order(tmp_path):
    calls = []

    class FakeRun(ReconHarness):
        def _open_session(self):
            calls.append("open"); return {"final_cookies": [{"name": "_px3", "value": "t"}]}
        def _drive_to_challenge(self, session):
            calls.append("drive")
        def _collect(self, session):
            calls.append("collect")
            return [], [], [{"name": "_px3", "value": "t"}], []
        def _close_session(self, session):
            calls.append("close")

    from perimeterx_solver.corpus import SampleCorpus
    h = FakeRun(corpus=SampleCorpus(root=str(tmp_path)), run_id="r1", meta={})
    sample = h.run()
    assert calls == ["open", "drive", "collect", "close"]
    assert sample.outcome == "pass"
    assert SampleCorpus(root=str(tmp_path)).golden().run_id == "r1"
