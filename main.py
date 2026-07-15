import aiohttp
import json
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger

class DaidaiManagerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 从AstrBot配置中读取呆呆面板的连接信息
        self.base_url = self.context.get_plugin_config().get("base_url", "http://192.168.5.1:5777/api")
        self.app_key = self.context.get_plugin_config().get("app_key", "")
        self.app_secret = self.context.get_plugin_config().get("app_secret", "")

    async def _call_api(self, endpoint: str, method: str = "GET", data: dict = None):
        """通用方法：调用呆呆面板的Open API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "X-App-Key": self.app_key,      # 认证方式请以实际API文档为准[reference:8]
            "X-App-Secret": self.app_secret
        }
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as resp:
                return await resp.json()
