# tests/perimeterx_solver/test_cookie_snapshotter.py
from perimeterx_solver.recon.cookie_snapshotter import PxCookieSnapshotter, PX_COOKIE_NAMES, is_px_cookie


def test_is_px_cookie():
    assert is_px_cookie("_px3")
    assert is_px_cookie("_pxhd")
    assert is_px_cookie("_pxff_abc")   # 前缀族
    assert not is_px_cookie("MUID")


def test_snapshot_filters_px_only():
    snap = PxCookieSnapshotter()
    m = snap.snapshot("after_hold", ts=1.0,
                      cookies=[{"name": "_px3", "value": "tok"}, {"name": "MUID", "value": "x"}])
    assert m.label == "after_hold"
    assert m.cookies == {"_px3": "tok"}


def test_diff_detects_new_clearance():
    snap = PxCookieSnapshotter()
    a = snap.snapshot("before", ts=1.0, cookies=[{"name": "_pxhd", "value": "h"}])
    b = snap.snapshot("after", ts=2.0, cookies=[{"name": "_pxhd", "value": "h"}, {"name": "_px3", "value": "t"}])
    assert snap.diff(a, b) == {"_px3": (None, "t")}
