"""Standalone Outlook registration loop. Continuously registers fresh
outlook accounts via ixBrowser + standalone register_outlook script, and
writes each success to _data_bundle/_outlook_pool/ as one JSON file per
record (email + password + session cookies).

The Replit batch (_batch_register.py / bs_register_step1.py) consumes these
via the `pool` email source — fully decoupled, so a slow self-reg attempt
never blocks the Replit signup pipeline.

Usage:
  python outlook_reg_loop.py                       # loop forever
  python outlook_reg_loop.py --count 20            # 20 attempts then exit
  python outlook_reg_loop.py --target-pool 10      # stop refilling once pool >= 10
  python outlook_reg_loop.py --max-press 8         # OUTLOOK_REG_MAX_PRESS
  python outlook_reg_loop.py --sleep 5             # gap between attempts (s)

★ PerimeterX 长按全自动方案（2026-06-11 实测）★：
  press-and-hold 是 IP 声誉主导。**干净住宅 IP 上自动长按直接过**（实测 1024proxy BE/VOO
  住宅 ~67%/次，每次 1-2 按；配本循环的每次 rotate_proxy_sid 换 IP + 失败重试 → 接近 100%）。
  关键是喂【干净、未被烧的住宅 IP 源】。原始失败都是 IP 被标记（见记忆 perimeterx-ip-reputation-burn）。
  配置（PowerShell）：
    $env:OUTLOOK_PROXIES="socks5://us.1024proxy.io:3000:sb7f3017-region-BE-sid-Q7GXp9aN-t-5:f3vxcmih"
    python outlook_reg_loop.py --count 20 --max-press 8
  本循环已：每次 rotate sid 换出口 IP、自动长按(register_outlook 默认)、成功存号(含 refresh_token)
  到 _outlook_pool/ 和 emails.txt、失败自动重试下一个干净 IP。

Reads HTTP_PROXY env for Clash routing (host:port form). Set
SELF_REG_SCRIPT_PATH to override standalone script location.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import string
import sys
import time
import importlib.util
import urllib.request
from datetime import datetime
from common.browser_provider import get_browser_provider

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ARTIFACT_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_DIR = os.path.join(ARTIFACT_DIR, "_outlook_pool")
# 账号注册侧消费的池（common/emails.next_email 读取），格式 email----password----token----clientid
EMAILS_POOL = os.path.join(ARTIFACT_DIR, "emails.txt")

STANDALONE_PATH = os.environ.get(
    "SELF_REG_SCRIPT_PATH",
    os.path.join(ARTIFACT_DIR, "register_outlook_standalone.py"),
)

# Optional Clash rotation between attempts. Without this, MS PerimeterX
# learns the egress IP after 1-2 signups and ERR_CONNECTION_CLOSEDs us out.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _clash_verge  # type: ignore
except ImportError:
    _clash_verge = None


def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def load_standalone():
    if not os.path.isfile(STANDALONE_PATH):
        log(f"standalone not found at {STANDALONE_PATH}", "ERR")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("_self_reg_standalone", STANDALONE_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    log(f"loaded standalone from {STANDALONE_PATH}")
    return m


def init_clash():
    """Connect to Clash controller. Returns (client, group_name) or (None, None)."""
    if _clash_verge is None:
        return None, None
    api = os.environ.get("CLASH_API", "").strip() or None
    secret = os.environ.get("CLASH_SECRET", "").strip()
    if not api:
        try:
            api = _clash_verge.auto_detect_api(secret=secret)
        except Exception as e:
            log(f"clash auto-detect failed: {e}", "WARN")
            return None, None
    if not api:
        return None, None
    try:
        client = _clash_verge.ClashClient(api=api, secret=secret)
    except Exception as e:
        log(f"clash client init failed: {e}", "WARN")
        return None, None
    group = (os.environ.get("CLASH_GROUP", "").strip() or "").strip()
    if not group or group.lower() == "auto":
        try:
            group = _clash_verge.auto_pick_group(client) or ""
        except Exception as e:
            log(f"clash auto-pick group failed: {e}", "WARN")
    if not group:
        log("clash: no usable group", "WARN")
        return None, None
    log(f"clash ready: api={api} group={group!r}")
    return client, group


def maybe_rotate(client, group, strategy="round_robin", max_latency_ms=6000,
                 mixed_port=7897):
    """Rotate to a fresh Clash node and verify egress IP actually changed.
    Uses rotate_with_verify which recurses into nested selector groups when
    the outer switch hits another group (e.g. GLOBAL -> 📲 Telegram is just
    another selector, not a real node)."""
    if client is None or not group:
        return None
    try:
        info = _clash_verge.rotate_with_verify(
            client, group, strategy=strategy,
            max_latency_ms=max_latency_ms,
            mixed_port=mixed_port,
            settle_sec=1.5,
        )
        if info.get("ip_changed"):
            log(f"clash IP {info.get('ip_before')} -> {info.get('ip_after')} (group={info.get('group')})")
        else:
            log(f"clash rotate: IP unchanged ({info.get('ip_before')})", "WARN")
        return info
    except Exception as e:
        log(f"clash rotate err: {type(e).__name__}: {e}", "WARN")
        return None


def clash_proxy_from_env():
    raw = (
        os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        or ""
    ).strip()
    if not raw:
        return None
    for pfx in ("http://", "https://", "socks5://"):
        if raw.lower().startswith(pfx):
            raw = raw[len(pfx):]
            break
    return raw.rstrip("/") or None




_SID_RE = re.compile(r"-sid-[^-]+-")
_SESSION_RE = re.compile(r"_session-[^_]+")


def rotate_proxy_sid(proxy_str):
    """轮换代理的粘性会话标识，每次注册换一个出口 IP。
    支持 1024proxy 的 -sid-XXXX- 和 IPRoyal 的 _session-XXXX 两种格式；
    不含会话标识的代理原样返回。"""
    if not proxy_str:
        return proxy_str
    new = "".join(random.choices(string.ascii_letters + string.digits, k=10))
    if "-sid-" in proxy_str:
        return _SID_RE.sub(f"-sid-{new}-", proxy_str, count=1)
    if "_session-" in proxy_str:
        return _SESSION_RE.sub(f"_session-{new}", proxy_str, count=1)
    return proxy_str


def count_pool():
    if not os.path.isdir(POOL_DIR):
        return 0
    try:
        return sum(1 for f in os.listdir(POOL_DIR) if f.endswith(".json"))
    except Exception:
        return 0


def append_to_emails_pool(email, password, refresh_token=None, client_id=None):
    """把成功号桥接进 emails.txt 池，供账号注册侧 common/emails.next_email 消费。
    有 refresh_token 就写真 token（消费侧纯 HTTP 取码）；没有则用占位符 fresh（回退 broker 浏览器取码）。"""
    try:
        existing = set()
        if os.path.isfile(EMAILS_POOL):
            with open(EMAILS_POOL, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        existing.add(line.split("----")[0].strip().lower())
        if email.lower() in existing:
            return
        tok = refresh_token or "fresh"
        cid = client_id or "fresh"
        with open(EMAILS_POOL, "a", encoding="utf-8") as f:
            f.write(f"{email}----{password}----{tok}----{cid}\n")
        log(f"emails.txt += {email} (token={'yes' if refresh_token else 'fresh'})", "OK")
    except Exception as e:
        log(f"append_to_emails_pool failed: {type(e).__name__}: {e}", "WARN")


def write_record(record):
    os.makedirs(POOL_DIR, exist_ok=True)
    safe = record["email"].replace("@", "_at_").replace("/", "_")
    fname = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:18] + f"_{safe}.json"
    tmp = os.path.join(POOL_DIR, fname + ".tmp")
    dst = os.path.join(POOL_DIR, fname)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        os.rename(tmp, dst)
    except Exception as e:
        log(f"write_record FAILED: {type(e).__name__}: {e}  (tmp={tmp})", "ERR")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise
    # Verify it actually landed.
    if os.path.isfile(dst):
        sz = os.path.getsize(dst)
        log(f"write_record OK: {dst}  ({sz} bytes)", "OK")
    else:
        log(f"write_record sus: {dst} missing right after rename!", "ERR")
    return fname


async def one_attempt(mod, proxy_str, idx):
    """Mirrors bs_register_step1.fetch_email_from_self_register's inline
    flow, but doesn't carry the breaker state — we're a dedicated loop and
    want to keep trying."""
    profile_id = None
    bb = get_browser_provider()
    try:
        ts = datetime.now().strftime("%m%d_%H%M%S")
        for _r in range(5):
            try:
                # Use our own create that picks coreVersion=146 (matches the
                # ixBrowser install on this machine). Standalone's hardcoded
                # 130 makes BB return 502.
                profile_id = bb.create_browser(name=f"outlook_loop_{ts}_{idx}", proxy_str=proxy_str)
                break
            except Exception as e:
                m = str(e)
                if "最大" in m or "超过" in m:
                    log("ixBrowser quota — cleanup_browsers(keep=2)", "WARN")
                    try: bb.cleanup_browsers(keep=2)
                    except Exception: pass
                    await asyncio.sleep(3)
                    continue
                if _r >= 4:
                    raise
                log(f"create_browser err (try {_r+1}/5): {m[:200]}", "WARN")
                await asyncio.sleep(3 + _r)
        if not profile_id:
            return None, None, [], None
        info = bb.open_browser(profile_id)
        ws = info.get("ws", "")
        if not ws:
            return None, None, [], None
        from playwright.async_api import async_playwright as _apw
        async with _apw() as p:
            browser = await p.chromium.connect_over_cdp(ws)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            # Scrub Chromium residual state so signup.live.com doesn't see a
            # stale identity from a previous session.
            try:
                await ctx.clear_cookies()
                for _pg in ctx.pages:
                    try:
                        c = await ctx.new_cdp_session(_pg)
                        await c.send("Network.clearBrowserCookies")
                        await c.send("Network.clearBrowserCache")
                        try: await c.detach()
                        except Exception: pass
                        break
                    except Exception:
                        pass
            except Exception:
                pass
            page = await ctx.new_page()
            # register_outlook 成功返回 3 元组 (email, password, graph)，失败返回 (None, None)。
            # 必须按下标取，不能解包成 2（否则成功时 ValueError）。
            result = await mod.register_outlook(page, ctx, idx)
            email = result[0] if result else None
            password = result[1] if result and len(result) > 1 else None
            graph = result[2] if result and len(result) > 2 else None
            cookies = []
            if email:
                try:
                    all_cookies = await ctx.cookies()
                    keep_domains = (
                        "outlook.", "live.com", "microsoftonline.",
                        "microsoft.com", "office.com", ".office365.",
                        "msn.com", "bing.com", "mail.live.com",
                    )
                    cookies = [
                        c for c in all_cookies
                        if any(d in (c.get("domain") or "") for d in keep_domains)
                    ]
                except Exception as e:
                    log(f"cookie export failed: {e}", "WARN")
        return email, password, cookies, graph
    finally:
        if profile_id:
            try:
                bb.close_browser(profile_id)
                await asyncio.sleep(2)
                bb.delete_browser(profile_id)
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=0,
                    help="run this many attempts then exit (0 = loop forever)")
    ap.add_argument("--target-pool", type=int, default=0,
                    help="stop registering once pool dir has this many records "
                         "(0 = no cap; producer always runs)")
    ap.add_argument("--max-press", default="3",
                    help="OUTLOOK_REG_MAX_PRESS — captcha press-and-hold cap")
    ap.add_argument("--timeout", type=int, default=180,
                    help="hard cap per attempt (seconds)")
    ap.add_argument("--sleep", type=int, default=5,
                    help="seconds between attempts (after fail or success)")
    ap.add_argument("--sleep-when-full", type=int, default=60,
                    help="seconds to sleep when pool is at target")
    args = ap.parse_args()

    os.environ.setdefault("OUTLOOK_REG_MAX_PRESS", args.max_press)
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    mod = load_standalone()
    # 优先用 OUTLOOK_PROXIES 的首个代理（保留 socks5:// 前缀）作为 ixBrowser
    # per-window 代理；为空再回退到 HTTP_PROXY/Clash 本地端口。
    _op = os.environ.get("OUTLOOK_PROXIES", "").replace(",", "\n").splitlines()
    proxy = next((p.strip() for p in _op if p.strip() and not p.strip().startswith("#")), None)
    if not proxy:
        proxy = clash_proxy_from_env()
    if not proxy:
        log("no proxy (OUTLOOK_PROXIES / HTTP_PROXY empty) — signup will likely fail", "WARN")
    else:
        log(f"using per-window proxy: {proxy}")

    # Initialize Clash controller for per-attempt node rotation. MS PerimeterX
    # learns the egress IP fast — without rotation we get ERR_CONNECTION_CLOSED
    # after 1-2 signups from the same node.
    clash_client, clash_group = init_clash()

    log(f"pool dir: {POOL_DIR}")
    os.makedirs(POOL_DIR, exist_ok=True)
    log(f"current pool size: {count_pool()}")

    n = 0
    succ = 0
    failed = 0
    while True:
        n += 1
        if args.count and n > args.count:
            log(f"reached --count {args.count}, exit (success={succ}, fail={failed})")
            break
        ps = count_pool()
        if args.target_pool and ps >= args.target_pool:
            log(f"pool at target ({ps}/{args.target_pool}) — sleep {args.sleep_when_full}s")
            time.sleep(args.sleep_when_full)
            continue
        # Rotate Clash node before each attempt so MS PX sees a fresh IP.
        maybe_rotate(clash_client, clash_group)
        # 每次注册换一个住宅代理 sid -> 新出口 IP，避免微软对固定 IP 风控
        attempt_proxy = rotate_proxy_sid(proxy)
        if attempt_proxy and attempt_proxy != proxy:
            _m = re.search(r"(?:-sid-|_session-)([^-_@]+)", attempt_proxy)
            log(f"proxy session -> {_m.group(1) if _m else '?'}")
        log(f"=== attempt #{n}  (pool={ps}, succ={succ}, fail={failed}) ===")
        t0 = time.time()
        email = password = None
        cookies = []
        graph = None
        try:
            email, password, cookies, graph = asyncio.run(
                asyncio.wait_for(one_attempt(mod, attempt_proxy, n), timeout=args.timeout)
            )
        except Exception as e:
            log(f"attempt raised {type(e).__name__}: {str(e)[:200]}", "WARN")
        elapsed = time.time() - t0
        if email and password:
            refresh_token = (graph or {}).get("refresh_token")
            client_id = (graph or {}).get("client_id")
            fname = write_record({
                "email": email,
                "password": password,
                "refresh_token": refresh_token,
                "client_id": client_id,
                "outlook_cookies": cookies,
                "source": "self-loop",
                "ts": datetime.now().isoformat(),
            })
            append_to_emails_pool(email, password, refresh_token, client_id)   # 桥接进账号注册池
            succ += 1
            log(f"OK in {elapsed:.1f}s: {email} (refresh_token={'yes' if refresh_token else 'no'}) "
                f"-> {fname} (pool now {count_pool()})", "OK")
            time.sleep(args.sleep)
            continue
        failed += 1
        log(f"FAIL in {elapsed:.1f}s (success rate {succ}/{n} = {100*succ/n:.0f}%)", "WARN")
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
