# perimeterx_solver/corpus.py
import json
import os

from .models import Sample


class SampleCorpus:
    """配对样本仓库（Repository）：按 outcome/run_id 落地与索引。

    布局：<root>/<outcome>/<run_id>/sample.json
    """

    def __init__(self, root="perimeterx_solver/corpus"):
        self.root = root

    def _dir(self, outcome, run_id):
        return os.path.join(self.root, outcome, run_id)

    def save(self, sample: Sample):
        d = self._dir(sample.outcome, sample.run_id)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sample.json"), "w", encoding="utf-8") as f:
            json.dump(sample.to_dict(), f, ensure_ascii=False, indent=2)

    def load(self, run_id) -> Sample:
        for outcome in ("pass", "fail"):
            p = os.path.join(self._dir(outcome, run_id), "sample.json")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    return Sample.from_dict(json.load(f))
        raise FileNotFoundError(run_id)

    def list(self, outcome=None):
        outcomes = (outcome,) if outcome else ("pass", "fail")
        out = []
        for oc in outcomes:
            base = os.path.join(self.root, oc)
            if not os.path.isdir(base):
                continue
            for rid in sorted(os.listdir(base)):
                p = os.path.join(base, rid, "sample.json")
                if os.path.exists(p):
                    with open(p, encoding="utf-8") as f:
                        out.append(Sample.from_dict(json.load(f)))
        return out

    def golden(self):
        passes = self.list(outcome="pass")
        return passes[0] if passes else None
