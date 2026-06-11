# tests/perimeterx_solver/test_script_dumper.py
from perimeterx_solver.recon.script_dumper import PxScriptDumper


def test_dump_hashes_and_stores(tmp_path):
    d = PxScriptDumper(out_dir=str(tmp_path))
    ref = d.dump("https://client.px-cloud.net/PXzC5j78di/main.min.js", "var a=1;")
    assert len(ref["sha256"]) == 64
    assert ref["url"].endswith("main.min.js")
    import os
    assert os.path.exists(ref["path"])


def test_same_content_same_hash(tmp_path):
    d = PxScriptDumper(out_dir=str(tmp_path))
    a = d.dump("u1", "same")
    b = d.dump("u2", "same")
    assert a["sha256"] == b["sha256"]
