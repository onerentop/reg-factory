"""进程管理器。用 multiprocessing.Process 实现真并发注册。

跨平台兼容（Windows spawn + Linux fork/spawn）。
每个注册任务在独立子进程中运行，有自己的 asyncio 事件循环。
"""

import multiprocessing
import asyncio
import uuid
import json
import time
import os
import sys
from typing import Any


def _fetch_proxy_from_manager() -> str:
    """从 Gateway 代理管理获取一个激活的代理。"""
    import random
    try:
        import requests as _req
        # proxies 显式禁用：取内部 /proxy 不受 os.environ 代理污染(否则失败→无代理注册)
        resp = _req.get("http://localhost:8000/proxy", timeout=5, proxies={"http": None, "https": None})
        proxy_list = resp.json().get("data", [])
        available = [p for p in proxy_list if p.get("status") in ("active", "available")]
        if available:
            s = random.choice(available)
            ptype = s.get("type", "socks5")
            host = s.get("host", "")
            port = s.get("port", "")
            user = s.get("username", "")
            pwd = s.get("password", "")
            if user and pwd:
                return f"{ptype}://{user}:{pwd}@{host}:{port}"
            return f"{ptype}://{host}:{port}"
    except Exception:
        pass
    return ""


def _worker_process(task_id: str, idx: int, proxy: str, config: dict, redis_url: str):
    """子进程入口。独立的 Python 进程，有自己的事件循环。"""
    # 确保项目根目录在 path 中
    services_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root_dir = os.path.dirname(services_dir)
    if services_dir not in sys.path:
        sys.path.insert(0, services_dir)
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    # 修复 stdio
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stdin.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # 加载 .env
    try:
        import config as _legacy_config  # noqa
    except Exception:
        pass

    # 设置 Redis 日志推送
    import redis as _redis
    try:
        r = _redis.from_url(redis_url)
        channel = f"task:{task_id}:logs"

        class RedisPrinter:
            def __init__(self, original, redis_client, ch):
                self._original = original
                self._redis = redis_client
                self._channel = ch

            def write(self, text):
                if self._original:
                    try:
                        self._original.write(text)
                    except Exception:
                        pass
                if text.strip():
                    try:
                        self._redis.publish(self._channel, json.dumps({
                            "type": "log", "message": text.strip(),
                        }))
                    except Exception:
                        pass
                return len(text)

            def flush(self):
                if self._original:
                    try:
                        self._original.flush()
                    except Exception:
                        pass

            def reconfigure(self, **kwargs):
                pass

            @property
            def encoding(self):
                return 'utf-8'

            @property
            def buffer(self):
                return getattr(self._original, 'buffer', None)

        sys.stdout = RedisPrinter(sys.stdout, r, channel)

    except Exception:
        r = None
        channel = None

    # 执行注册
    async def _run():
        import asyncio as _aio
        # 并发错开启动：第 idx 个任务延迟，避开多 ixBrowser 窗口同时创建/warming
        # 的资源竞争峰值。WebSearch 证实 stagger startup 是并发浏览器自动化标准做法
        # (无错开 >8 实例崩溃率 >43%)；注册是重流程，用秒级(默认 8s/任务)而非毫秒级。
        _stagger = (config or {}).get("stagger_seconds", 8)
        if idx > 0 and _stagger > 0:
            print(f"[process#{idx}] 并发错开，等 {idx * _stagger}s 再启动")
            await _aio.sleep(idx * _stagger)
        from worker.step_engine import FlowRegistry
        flow = FlowRegistry.get("outlook")
        context = {"idx": idx, "proxy": proxy, **(config or {})}
        step_results = await flow.run(context)
        success = all(sr.success for sr in step_results)
        email = context.get("email", "")
        password = context.get("password", "")

        # 保存到 Account Service
        if success and email:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    create_resp = await client.post("http://localhost:8002/accounts", json={
                        "email": email, "password": password, "platform": "outlook",
                        "total_steps": len(step_results),
                        "metadata": {"proxy": proxy[:30] if proxy else ""},
                    })
                    account_data = create_resp.json().get("data", {})
                    account_id = account_data.get("id")
                    if account_id:
                        raw_token = context.get("refresh_token", "")
                        if isinstance(raw_token, dict):
                            refresh_token = raw_token.get("refresh_token", "")
                        else:
                            refresh_token = str(raw_token) if raw_token else ""
                        await client.put(f"http://localhost:8002/accounts/{account_id}", json={
                            "status": "success", "current_step": len(step_results),
                            "tokens": {"refresh_token": refresh_token, "client_id": "9e5f94bc-e8a4-4e73-b8be-63364c29d753"} if refresh_token else None,
                        })
                print(f"[process#{idx}] saved: {email}")
            except Exception as e:
                print(f"[process#{idx}] save failed: {e}")

        return {"success": success, "email": email, "has_token": bool(context.get("refresh_token"))}

    try:
        result = asyncio.run(_run())
    except Exception as e:
        result = {"success": False, "email": "", "error": str(e)}

    # 发送完成信号 + 结果
    if r and channel:
        try:
            r.publish(channel, json.dumps({"type": "result", "data": result}))
            r.publish(channel, json.dumps({"type": "done"}))
            r.close()
        except Exception:
            pass


class TaskManager:
    """管理注册子进程。Gateway 内使用，不依赖 Celery。"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis_url = redis_url
        self._tasks: dict[str, dict] = {}

    def submit(self, idx: int = 0, proxy: str = "", config: dict | None = None) -> str:
        """提交一个注册任务，返回 task_id。"""
        task_id = str(uuid.uuid4())
        p = multiprocessing.Process(
            target=_worker_process,
            args=(task_id, idx, proxy, config or {}, self._redis_url),
            daemon=True,
        )
        p.start()
        self._tasks[task_id] = {
            "process": p,
            "pid": p.pid,
            "status": "running",
            "start_time": time.time(),
            "result": None,
        }
        return task_id

    def get_status(self, task_id: str) -> dict:
        """查询任务状态。"""
        task = self._tasks.get(task_id)
        if not task:
            return {"status": "unknown", "task_id": task_id}

        p = task["process"]
        if p.is_alive():
            elapsed = int(time.time() - task["start_time"])
            return {"status": "running", "task_id": task_id, "elapsed": elapsed}
        else:
            task["status"] = "completed"
            return {
                "status": "completed",
                "task_id": task_id,
                "exitcode": p.exitcode,
                "elapsed": int(time.time() - task["start_time"]),
            }

    def get_all_statuses(self) -> list[dict]:
        """查询所有任务状态。"""
        return [self.get_status(tid) for tid in self._tasks]

    def cleanup(self, max_age: int = 3600) -> int:
        """清理已完成的旧任务。"""
        now = time.time()
        to_remove = [tid for tid, t in self._tasks.items()
                     if not t["process"].is_alive() and now - t["start_time"] > max_age]
        for tid in to_remove:
            del self._tasks[tid]
        return len(to_remove)


# 全局单例
task_manager = TaskManager()
