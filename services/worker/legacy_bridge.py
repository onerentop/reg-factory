"""Legacy 适配桥。让新架构 import 根目录下的旧注册脚本。

Usage:
    from worker.legacy_bridge import LegacyBridge
    bridge = LegacyBridge()
    bridge.ensure_importable()
    from common.browser import open_and_connect, teardown, inject_stealth
    from common.sms import get_phone, get_code, release
"""

import os
import sys


class LegacyBridge:
    """将项目根目录加入 sys.path，使旧脚本可被 import。"""

    def __init__(self):
        self._root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)
        )))

    @property
    def project_root(self) -> str:
        return self._root

    def ensure_importable(self) -> None:
        if self._root not in sys.path:
            sys.path.insert(0, self._root)
        self._patch_stdio()

    @staticmethod
    def _patch_stdio() -> None:
        """旧脚本顶层有 sys.stdout/stdin.reconfigure()，
        pytest 等测试运行器的 IO 代理不支持该方法。"""
        if not hasattr(sys.stdin, "reconfigure"):
            sys.stdin = open(os.devnull, "r")
        if not hasattr(sys.stdout, "reconfigure"):
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer if hasattr(sys.stdout, 'buffer') else open(os.devnull, 'wb'), encoding='utf-8')
        if not hasattr(sys.stderr, "reconfigure"):
            pass

    def get_config(self, key: str, default: str = "") -> str:
        self.ensure_importable()
        try:
            import config as legacy_config
            return getattr(legacy_config, key, default)
        except ImportError:
            return default
