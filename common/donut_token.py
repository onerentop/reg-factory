# -*- coding: utf-8 -*-
"""
common/donut_token.py — 解密 donutbrowser 本地 API token。

donut 把 api_token.dat 用 Argon2(id)+AES-GCM 加密存储，密钥 = Argon2(vault_password)。
vault 密码默认 donutbrowser-api-vault-password（src-tauri/build.rs 未设环境变量时注入）。
本模块供 provider 导入使用；CLI 入口在 scripts/donut_token.py。

关键格式细节（踩坑记录）：
  - 盐是 Rust SaltString::encode_b64 生成，url-safe B64 无填充，需补 '=' 再解。
  - Argon2::default() 参数: m=19456 KiB(19MiB), t=2, p=1, output_len=32。
  - 文件头 "DBAPI" + version(1) + salt_len(1) + salt(b64) + nonce(12) + ct_len(4 LE) + ciphertext。
"""

import base64
import os
import struct

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

# 与 src-tauri/build.rs 默认注入一致
DEFAULT_VAULT_PASSWORD = "donutbrowser-api-vault-password"

# Argon2::default() 参数（argon2 0.5.3 src/params.rs: DEFAULT_M_COST=19*1024, T_COST=2, P_COST=1）
ARGON2_M_COST = 19456
ARGON2_T_COST = 2
ARGON2_P_COST = 1


def find_token_file():
    """定位 api_token.dat，优先 dev 数据目录（本机跑的是 debug 构建）。"""
    appdata = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(appdata, "DonutBrowserDev", "settings", "api_token.dat"),
        os.path.join(appdata, "DonutBrowser", "settings", "api_token.dat"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def decrypt(token_path, vault_password=DEFAULT_VAULT_PASSWORD):
    """按 settings_manager.store_api_token 的格式反向解密。返回明文 token 或 None。"""
    with open(token_path, "rb") as f:
        raw = f.read()

    if raw[:5] != b"DBAPI":
        raise ValueError(f"文件头不是 DBAPI: {token_path}")
    offset = 5
    offset += 1  # version
    salt_len = raw[offset]
    offset += 1
    salt_b64 = raw[offset:offset + salt_len].decode("utf-8")
    offset += salt_len
    nonce = raw[offset:offset + 12]
    offset += 12
    ct_len = struct.unpack("<I", raw[offset:offset + 4])[0]
    offset += 4
    ciphertext = raw[offset:offset + ct_len]

    if not HAVE_CRYPTO:
        raise RuntimeError("需要 cryptography 库: pip install cryptography")

    # Rust SaltString::encode_b64 用 url-safe B64（无填充），补 '=' 再解
    salt = base64.urlsafe_b64decode(salt_b64 + "=" * (-len(salt_b64) % 4))

    key = Argon2id(
        salt=salt,
        length=32,
        iterations=ARGON2_T_COST,
        lanes=ARGON2_P_COST,
        memory_cost=ARGON2_M_COST,
    ).derive(bytes(vault_password, "utf-8"))

    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def load_token():
    """从 token 文件解密 token；找不到或解密失败返回 None。"""
    token_file = find_token_file()
    if not token_file:
        return None
    try:
        return decrypt(token_file)
    except Exception:
        return None
