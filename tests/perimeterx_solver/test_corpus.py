# tests/perimeterx_solver/test_corpus.py
from perimeterx_solver.corpus import SampleCorpus
from perimeterx_solver.models import Sample, CapturedRequest


def test_save_load_roundtrip(tmp_path):
    c = SampleCorpus(root=str(tmp_path))
    s = Sample(run_id="r1", outcome="fail")
    s.requests.append(CapturedRequest(url="u", method="POST"))
    c.save(s)
    loaded = c.load("r1")
    assert loaded.outcome == "fail"
    assert loaded.requests[0].url == "u"


def test_list_and_golden(tmp_path):
    c = SampleCorpus(root=str(tmp_path))
    c.save(Sample(run_id="f1", outcome="fail"))
    c.save(Sample(run_id="p1", outcome="pass"))
    assert {s.run_id for s in c.list()} == {"f1", "p1"}
    assert {s.run_id for s in c.list(outcome="fail")} == {"f1"}
    assert c.golden().run_id == "p1"


def test_golden_none_when_no_pass(tmp_path):
    c = SampleCorpus(root=str(tmp_path))
    c.save(Sample(run_id="f1", outcome="fail"))
    assert c.golden() is None
