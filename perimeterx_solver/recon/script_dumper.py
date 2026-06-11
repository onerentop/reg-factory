# perimeterx_solver/recon/script_dumper.py
import hashlib
import os


class PxScriptDumper:
    """抓 collector/挑战脚本原文 + sha256 + 落盘（应对 VM 轮换：钉死版本）。"""

    def __init__(self, out_dir="perimeterx_solver/corpus/_scripts"):
        self.out_dir = out_dir

    def dump(self, url: str, text: str) -> dict:
        os.makedirs(self.out_dir, exist_ok=True)
        sha = hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()
        path = os.path.join(self.out_dir, f"{sha}.js")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text or "")
        return {"url": url, "sha256": sha, "path": path}
