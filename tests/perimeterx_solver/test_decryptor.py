# tests/perimeterx_solver/test_decryptor.py
import base64
import os

from perimeterx_solver.analysis.decryptor import Px2Decryptor, PayloadDecryptor

FIX = os.path.join(os.path.dirname(__file__), "real_payload.b64")
GOLDEN_PH = os.path.join(os.path.dirname(__file__), "golden_presshold.b64")


def _enc(plaintext: bytes) -> str:
    """构造 PX 格式密文：XOR 0x32 → base64。"""
    return base64.b64encode(bytes(c ^ 0x32 for c in plaintext)).decode()


def test_px2_is_strategy():
    assert issubclass(Px2Decryptor, PayloadDecryptor)


def test_px2_roundtrip_synthetic():
    pt = b'[{"t":"x","d":{"a":1,"url":"https://x"}}]'
    assert Px2Decryptor().decrypt(_enc(pt)) == pt


def test_px2_strips_payload_prefix_and_trailing_fields():
    pt = b'{"k":"v"}'
    assert Px2Decryptor().decrypt("payload=" + _enc(pt) + "&seq=1") == pt


def test_px2_decrypts_real_collector_payload():
    blob = open(FIX, encoding="utf-8").read().strip()
    out = Px2Decryptor().decrypt(blob)
    assert out.startswith(b'[{"t":"')
    assert b"hsprotect.net" in out
    assert b"PXzC5j78di" in out
    assert b"session_id" in out


def test_px2_handles_malformed_length():
    # len%4==1 的畸形/截断 base64 不应崩溃（容错截断）
    Px2Decryptor().decrypt("A" * 37)  # 37 % 4 == 1


def test_px2_decrypts_golden_presshold_telemetry():
    # 真人 PASS 长按遥测黄金样本：含 pointerdown/up + #px-captcha 目标
    blob = open(GOLDEN_PH, encoding="utf-8").read().strip()
    out = Px2Decryptor().decrypt(blob).decode("latin1")
    assert "#px-captcha" in out
    assert "pointerdown" in out and "pointerup" in out
    assert "de-DE" in out
