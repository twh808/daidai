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
        # 强制输出日志，确认插件被加载
        logger.info("===== 呆呆面板插件加载成功！=====")
        logger.info(f"base_url: {self.base_url}")
        logger.info(f"app_key 已设置: {bool(self.app_key)}")
        logger.info(f"app_secret 已设置: {bool(self.app_secret)}")

    async def _get_token(self):
        if self.token and self.token_expiry > time.time():
            return self.token
        token_url = f"http://192.168.5.1:5777/api/open-api/token"
        payload = {"app_key": self.app_key, "app_secret": self.app_secret}
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"获取 Token 失败，状态码：{resp.status}，响应：{error_text}")
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
        headers = {"Authorization": f"Bearer {token}"}
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

    @filter.command("envlist")
    async def envlist(self, event: AstrMessageEvent):
        '''测试指令：/envlist'''
        try:
            result = await self._call_api("envs?page=1&page_size=100", method="GET")
            envs = result.get("data", [])
            if not envs:
                yield event.plain_result("📭 当前没有环境变量")
            else:
                msg = "📋 环境变量列表：\n"
                for env in envs:
                    name = env.get("name", "未命名")
                    value = env.get("value", "")
                    msg += f"- {name} = {value}\n"
                yield event.plain_result(msg)
        except Exception as e:
            yield event.plain_result(f"❌ 错误：{str(e)}")
