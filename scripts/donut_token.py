# -*- coding: utf-8 -*-
"""
scripts/donut_token.py — 解密 donutbrowser 本地 API token（CLI 入口）。

用法: python scripts/donut_token.py
解密逻辑在 common/donut_token.py。
"""

import os
import sys

# 让 common 包可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.donut_token import find_token_file, decrypt


def main():
    token_file = find_token_file()
    if not token_file:
        print("未找到 api_token.dat")
        sys.exit(1)
    print(f"token 文件: {token_file}")
    try:
        token = decrypt(token_file)
    except Exception as e:
        print(f"解密失败: {e}")
        sys.exit(1)
    print(f"明文 token: {token[:8]}...{token[-4:]}  (len={len(token)})")
    print(f"DONUT_API_TOKEN={token}")


if __name__ == "__main__":
    main()
