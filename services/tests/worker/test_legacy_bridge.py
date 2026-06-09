import os
import sys
from worker.legacy_bridge import LegacyBridge


def test_legacy_bridge_resolves_root():
    bridge = LegacyBridge()
    root = bridge.project_root
    assert os.path.isdir(root)

def test_legacy_path_added():
    bridge = LegacyBridge()
    bridge.ensure_importable()
    assert bridge.project_root in sys.path

def test_get_config_missing():
    bridge = LegacyBridge()
    val = bridge.get_config("NONEXISTENT_KEY_12345", "fallback")
    assert val == "fallback"
