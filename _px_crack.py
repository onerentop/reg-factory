# -*- coding: utf-8 -*-
"""一次性：从钉死 main.min.js 挖自定义 base64 字母表，解 collector payload。"""
import json, re, sys, glob
sys.stdout.reconfigure(encoding="utf-8")

SCRIPT = glob.glob("perimeterx_solver/corpus/_scripts/*.js")[0]
src = open(SCRIPT, encoding="utf-8", errors="replace").read()
print(f"script={SCRIPT} len={len(src)}")

# 取一个真实 payload 值
ev = json.load(open("_px_events.json", encoding="utf-8"))
eg = [e["data"]["body"] for e in ev
      if e["kind"] in ("egress_xhr", "egress_fetch") and "collector" in e["data"].get("url", "")]
payload = [b.split("payload=", 1)[1].split("&", 1)[0] for b in eg if "payload=" in b][0]
pchars = set(payload) - {"="}
print(f"payload len={len(payload)} 独立字符数={len(pchars)}")

# 搜候选自定义 base64 字母表：长度 60-70 的字符串字面量，含我们观察到的所有 payload 字符
cands = []
for m in re.finditer(r"""['"`]([!-~]{60,70})['"`]""", src):
    s = m.group(1)
    if len(set(s)) >= 60 and pchars.issubset(set(s)):
        cands.append(s)
# 去重
seen = set(); uniq = []
for c in cands:
    if c not in seen:
        seen.add(c); uniq.append(c)
print(f"候选字母表(含全部payload字符) {len(uniq)} 个:")
for c in uniq:
    print("  ", repr(c))


def custom_b64decode(data, alphabet):
    lookup = {c: i for i, c in enumerate(alphabet)}
    data = data.rstrip("=")
    bits = nbits = 0
    out = bytearray()
    for c in data:
        if c not in lookup:
            return None
        bits = (bits << 6) | lookup[c]
        nbits += 6
        if nbits >= 8:
            nbits -= 8
            out.append((bits >> nbits) & 0xFF)
    return bytes(out)


def printable(b):
    return sum(1 for c in b if 32 <= c < 127 or c in (9, 10, 13)) / max(1, len(b))


print("\n=== 逐候选字母表解码 ===")
for alpha in uniq:
    for al in (alpha, alpha[::-1]):  # 也试反序
        dec = custom_b64decode(payload, al[:64])
        if dec is None:
            continue
        pr = printable(dec)
        head = bytes(c if 32 <= c < 127 else 46 for c in dec[:100])
        flag = " <== 像明文!" if pr > 0.9 else ""
        print(f"  alpha={al[:16]}... printable={pr:.2f}{flag}")
        if pr > 0.85:
            print("    PT[:160]:", bytes(c if 32 <= c < 127 else 46 for c in dec[:160]))
