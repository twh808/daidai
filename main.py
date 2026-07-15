import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger

class DaidaiManagerPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        if config is None:
            config = {}
        self.base_url = config.get("base_url", "http://192.168.5.1:5777/api")
        self.app_key = config.get("app_key", "")
        self.app_secret = config.get("app_secret", "")

    async def _call_api(self, endpoint: str, method: str = "POST", data: dict = None):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "X-App-Key": self.app_key,
            "X-App-Secret": self.app_secret
        }
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as resp:
                return await resp.json()

    @filter.command("运行脚本")
    async def run_script(self, event: AstrMessageEvent, script_name: str):
        '''运行呆呆面板中的脚本：/运行脚本 脚本名'''
        try:
            # ⚠️ 请根据 Apifox 文档确认实际端点
            result = await self._call_api("/script/run", data={"name": script_name})
            if result.get("code") == 0:
                yield event.plain_result(f"✅ 脚本 {script_name} 已成功运行！")
            else:
                yield event.plain_result(f"❌ 运行失败：{result.get('msg', '未知错误')}")
        except Exception as e:
            logger.error(f"调用呆呆面板API失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    @filter.command("修改环境变量")
    async def set_env(self, event: AstrMessageEvent, key: str, value: str):
        '''修改环境变量：/修改环境变量 变量名 变量值'''
        try:
            # ⚠️ 请根据 Apifox 文档确认实际端点
            result = await self._call_api("/env/update", data={"key": key, "value": value})
            if result.get("code") == 0:
                yield event.plain_result(f"✅ 环境变量 {key} 已更新为 {value}")
            else:
                yield event.plain_result(f"❌ 修改失败：{result.get('msg', '未知错误')}")
        except Exception as e:
            logger.error(f"调用呆呆面板API失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")
