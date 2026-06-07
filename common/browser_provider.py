# -*- coding: utf-8 -*-
"""
common/browser_provider.py — 指纹浏览器窗口抽象契约 + 工厂。

方法名与返回形状对齐历史封装契约，便于上层零改造迁移：
    p = get_browser_provider()
    pid = p.create_browser(name="chatgpt_xxx")
    data = p.open_browser(pid)          # {"ws": ..., "http": ...}
    p.close_browser(pid); p.delete_browser(pid)
"""

from abc import ABC, abstractmethod


class BrowserProvider(ABC):
    @abstractmethod
    def create_browser(self, name="reg", proxy_str=None, **kwargs):
        """创建窗口，返回 profile_id。proxy_str 为空=直连。"""

    @abstractmethod
    def open_browser(self, profile_id):
        """打开窗口，返回 {"ws": <cdp ws/http endpoint>, "http": <debug addr>}。"""

    @abstractmethod
    def close_browser(self, profile_id):
        """关闭窗口（吞异常）。"""

    @abstractmethod
    def delete_browser(self, profile_id):
        """删除窗口配置（吞异常）。"""

    @abstractmethod
    def cleanup_browsers(self, keep=0):
        """删除窗口释放配额，保留最新 keep 个，返回删除数。"""

    @abstractmethod
    def list_browsers(self, page=0, page_size=100):
        """返回 {"data": {"list": [{"id","name","remark","seq"}, ...]}}。"""

    @abstractmethod
    def select_browser(self):
        """交互式选择或新建窗口，返回 profile_id。"""


_PROVIDER = None


def get_browser_provider():
    """返回全局单例 provider（当前固定 ixBrowser）。"""
    global _PROVIDER
    if _PROVIDER is None:
        from common.ixbrowser_provider import IXBrowserProvider
        _PROVIDER = IXBrowserProvider()
    return _PROVIDER
