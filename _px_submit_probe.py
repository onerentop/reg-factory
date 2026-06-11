# -*- coding: utf-8 -*-
"""🔴 Phase2 提交探针：把黄金长按 collector body 重放到端点，看响应(校验顺序/过码格式/session绑定)。
用法：python _px_submit_probe.py "<proxy>"
"""
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import requests
import config  # noqa
from perimeterx_solver.corpus import SampleCorpus
from perimeterx_solver.classify import parse_collector_body
from perimeterx_solver.analysis.decryptor import Px2Decryptor
from register_outlook_standalone import _proxy_for_requests

URL = "https://collector-PXzC5j78di.hsprotect.net/api/v2/msft"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")


def main(proxy):
    dec = Px2Decryptor()
    g = SampleCorpus().golden()
    ph = None
    for r in g.requests:
        cp = parse_collector_body(r.req_body)
        if cp.encrypted_blob and b"#px-captcha" in dec.decrypt(cp.encrypted_blob):
            ph = r
            break
    if not ph:
        print("[submit] 未找到长按 collector 载荷")
        return
    print(f"[submit] 重放长按 body len={len(ph.req_body)} 字段={[s.split('=')[0] for s in ph.req_body.split('&')][:10]}")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://iframe.hsprotect.net",
        "Referer": "https://iframe.hsprotect.net/",
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    if proxy and "@" in proxy:
        proxies = {"http": proxy, "https": proxy}   # 已是 scheme://user:pass@host:port
    elif proxy:
        proxies = _proxy_for_requests(proxy)
    else:
        proxies = None
    try:
        r = requests.post(URL, data=ph.req_body.encode(), headers=headers, proxies=proxies, timeout=25)
    except Exception as e:
        print(f"[submit] 请求异常: {type(e).__name__}: {e}")
        return
    print(f"[submit] status={r.status_code}")
    print(f"[submit] resp headers: {dict(r.headers)}")
    sc = r.headers.get("set-cookie", "")
    print(f"[submit] Set-Cookie 含 _px3: {'_px3' in sc}  含 _pxhd: {'_pxhd' in sc}")
    print(f"[submit] body[:600]: {r.text[:600]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
