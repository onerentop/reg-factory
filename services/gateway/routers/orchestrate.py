from fastapi import APIRouter

from shared.base_schema import ApiResponse

router = APIRouter()


@router.post("/orchestrate/all-platforms", response_model=ApiResponse)
async def orchestrate_all_platforms(body: dict):
    from worker.tasks import register_all_platforms
    task = register_all_platforms.delay(
        body["email"], body["password"],
        body.get("platforms", ["claude", "chatgpt", "grok"]),
        body.get("config", {}),
    )
    return ApiResponse(data={"task_id": task.id, "status": "queued"})


@router.post("/orchestrate/full-flow", response_model=ApiResponse)
async def orchestrate_full_flow(body: dict):
    from worker.tasks import full_flow
    task = full_flow.delay(
        body.get("count", 1),
        body.get("platforms", ["claude", "chatgpt", "grok"]),
        body.get("config", {}),
    )
    return ApiResponse(data={"task_id": task.id, "status": "queued"})
