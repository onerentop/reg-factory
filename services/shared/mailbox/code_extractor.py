"""从邮件内容中提取验证码或 magic link。从 common/mailbox.py 迁移。"""

import re
import asyncio
import logging
from typing import Any

from shared.mailbox.graph_client import GraphClient

logger = logging.getLogger(__name__)


class CodeExtractor:
    """从 Outlook 邮件中提取验证码或 magic link。"""

    def __init__(self, graph_client: GraphClient | None = None):
        self._graph = graph_client or GraphClient()

    async def extract_code(
        self,
        refresh_token: str,
        sender_hint: str = "",
        subject_hint: str = "",
        code_regex: str = r"\b(\d{6})\b",
        timeout: int = 300,
        poll_interval: int = 10,
    ) -> str | None:
        elapsed = 0
        while elapsed < timeout:
            access_token = await self._graph.get_access_token(refresh_token)
            if not access_token:
                logger.warning("Failed to get access token")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue

            messages = await self._graph.fetch_from_folders(access_token)
            for msg in messages:
                if not self._match_message(msg, sender_hint, subject_hint):
                    continue
                body = msg.get("body", {}).get("content", "")
                match = re.search(code_regex, body)
                if match:
                    return match.group(1)

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning(f"Code extraction timed out after {timeout}s")
        return None

    async def extract_magic_link(
        self,
        refresh_token: str,
        sender_hint: str = "",
        subject_hint: str = "",
        link_regex: str = r'https://[^\s"<>]+',
        timeout: int = 300,
        poll_interval: int = 10,
    ) -> str | None:
        elapsed = 0
        while elapsed < timeout:
            access_token = await self._graph.get_access_token(refresh_token)
            if not access_token:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue

            messages = await self._graph.fetch_from_folders(access_token)
            for msg in messages:
                if not self._match_message(msg, sender_hint, subject_hint):
                    continue
                body = msg.get("body", {}).get("content", "")
                match = re.search(link_regex, body)
                if match:
                    link = match.group(0)
                    if link.startswith("https://"):
                        return link

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        return None

    @staticmethod
    def _match_message(msg: dict, sender_hint: str, subject_hint: str) -> bool:
        if sender_hint:
            sender = msg.get("from", {}).get("emailAddress", {}).get("address", "")
            if sender_hint.lower() not in sender.lower():
                return False
        if subject_hint:
            subject = msg.get("subject", "")
            if subject_hint.lower() not in subject.lower():
                return False
        return True
