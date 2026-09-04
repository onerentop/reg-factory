"""Outlook / Google 本机注册任务处理器。"""

from worker.tasks.registration import register_account, register_outlook_single, retry_from_step
