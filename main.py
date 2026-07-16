import aiohttp
import time
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger

class DaidaiManagerPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        if config is None:
            config = {}
        self.base_url = config.get("base_url", "http://192.168.5.1:5777/api/v1")
        self.app_key = config.get("app_key", "")
        self.app_secret = config.get("app_secret", "")
        self.token = None
        self.token_expiry = 0
        logger.info("✅ 呆呆面板插件加载成功")

    async def _get_token(self):
        if self.token and self.token_expiry > time.time():
            return self.token
        token_url = f"http://192.168.5.1:5777/api/open-api/token"
        payload = {"app_key": self.app_key, "app_secret": self.app_secret}
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"获取 Token 失败：{error_text}")
                result = await resp.json()
                token = result.get("data", {}).get("access_token")
                if not token:
                    raise Exception("Token 响应中未找到 access_token")
                expires_in = result.get("data", {}).get("expires_in", 86400)
                self.token_expiry = time.time() + expires_in - 60
                self.token = token
                return token

    async def _call_api(self, endpoint: str, method: str = "GET", data: dict = None):
        token = await self._get_token()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as resp:
                if resp.status == 401:
                    self.token = None
                    self.token_expiry = 0
                    return await self._call_api(endpoint, method, data)
                try:
                    return await resp.json()
                except:
                    return {"error": f"HTTP {resp.status}", "text": await resp.text()}

    # 使用装饰器，并返回 MessageChain（不使用 yield）
    @filter.command("envlist")
    async def envlist(self, event: AstrMessageEvent):
        '''获取环境变量列表：/envlist'''
        try:
            result = await self._call_api("envs?page=1&page_size=100", method="GET")
            envs = result.get("data", [])
            if not envs:
                return event.plain_result("📭 当前没有环境变量")
            else:
                msg = "📋 环境变量列表：\n"
                for env in envs:
                    name = env.get("name", "未命名")
                    value = env.get("value", "")
                    group = env.get("group", "默认分组")
                    msg += f"- {name} = {value} (分组: {group})\n"
                return event.plain_result(msg)
        except Exception as e:
            logger.error(f"获取环境变量列表失败: {e}")
            return event.plain_result(f"❌ 请求失败：{str(e)}")
