import httpx as _httpx

from fastapi import APIRouter, Request

from gateway.deps import _SMS_URL, _ACCOUNT_URL, _CONFIG_URL

router = APIRouter()


async def _proxy_request(request: Request, target_base: str, path: str) -> dict:
    """通用代理转发。"""
    try:
        # trust_env=False：转发到内部微服务(localhost)永不走代理。
        # 否则 os.environ 的 HTTP_PROXY(extract-graph-token 等会设)会让内部转发
        # 误走代理，代理回不到 localhost → 畸形/空响应 → JSONDecodeError → 500。
        async with _httpx.AsyncClient(timeout=30, trust_env=False) as client:
            url = f"{target_base}{path}"
            body = await request.body()
            resp = await client.request(
                method=request.method,
                url=url,
                content=body if body else None,
                headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
                params=dict(request.query_params),
            )
            return resp.json()
    except Exception as e:
        print(f"[proxy] ERROR {request.method} {target_base}{path}: {e}")
        raise


@router.api_route("/sms/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_sms(request: Request, path: str):
    return await _proxy_request(request, _SMS_URL, f"/sms/{path}")


@router.api_route("/accounts", methods=["GET", "POST"])
@router.api_route("/accounts/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_accounts(request: Request, path: str = ""):
    target = f"/accounts/{path}" if path else "/accounts"
    return await _proxy_request(request, _ACCOUNT_URL, target)


@router.api_route("/config/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_config(request: Request, path: str):
    return await _proxy_request(request, _CONFIG_URL, f"/config/{path}")
