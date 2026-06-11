# perimeterx_solver/analysis/decryptor.py
"""collector 载荷解密（Strategy）。

实测算法（2026-06-11，原始 CDP 调试器断在编码器栈 + 已知明文攻击确证）：
    payload = 标准base64( 单字节 XOR 0x32 ( JSON明文 ) )
明文是 JSON 结构：`[{"t":"<混淆类型id>","d":{"<混淆字段名base64>":值,...}}]`，
部分 value 是嵌入的二进制指纹哈希（canvas/audio/webgl），故返回 bytes，不强行 json.loads。
"""
import base64
import re

_B64_ONLY = re.compile(r"[^A-Za-z0-9+/]")


class PayloadDecryptor:
    """collector 密文 → 明文字节 的策略接口（Strategy）。PX 换版可换实现。"""

    def decrypt(self, encrypted_blob: str, context: dict = None) -> bytes:
        raise NotImplementedError


class Px2Decryptor(PayloadDecryptor):
    """Microsoft PerimeterX（appId PXzC5j78di）collector 载荷解密：base64 → XOR 0x32。"""

    XOR_KEY = 0x32

    def decrypt(self, encrypted_blob: str, context: dict = None) -> bytes:
        s = encrypted_blob or ""
        if s.startswith("payload="):
            s = s[len("payload="):]
        s = s.split("&", 1)[0]              # 容错：body 里 payload 后可能跟其它表单字段
        s = _B64_ONLY.sub("", s)            # 剔除非标准base64字符(捕获伪影/杂散)+去原padding
        raw = base64.b64decode(s + "=" * (-len(s) % 4))
        return bytes(c ^ self.XOR_KEY for c in raw)

    def decrypt_text(self, encrypted_blob: str, context: dict = None) -> str:
        """latin1 文本视图（二进制指纹值保留为高位字符），便于人读结构。"""
        return self.decrypt(encrypted_blob, context).decode("latin1")
