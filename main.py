import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger

# 插件主类，必须继承 Star[reference:11]
class DaidaiManagerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 从AstrBot配置中读取信息
        plugin_config = self.context.get_plugin_config()
        self.base_url = plugin_config.get("base_url", "http://192.168.5.1:5777/api")
        self.app_key = plugin_config.get("app_key", "")
        self.app_secret = plugin_config.get("app_secret", "")

    async def _call_api(self, endpoint: str, method: str = "POST", data: dict = None):
        """通用方法：调用呆呆面板的 API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "X-App-Key": self.app_key,      # ⚠️ 认证方式请以实际API文档为准
            "X-App-Secret": self.app_secret
        }
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as resp:
                return await resp.json()

    # 注册指令，用户发送 /运行脚本 脚本名 触发[reference:12]
    @filter.command("运行脚本")
    async def run_script(self, event: AstrMessageEvent, script_name: str):
        '''运行呆呆面板中的脚本：/运行脚本 脚本名'''
        try:
            # ⚠️ 实际API端点请查阅Apifox文档确认
            result = await self._call_api("/script/run", data={"name": script_name})
            if result.get("code") == 0:
                yield event.plain_result(f"✅ 脚本 {script_name} 已成功运行！")
            else:
                yield event.plain_result(f"❌ 运行失败：{result.get('msg', '未知错误')}")
        except Exception as e:
            logger.error(f"调用呆呆面板API失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    # 注册指令，用户发送 /修改环境变量 变量名 值 触发
    @filter.command("修改环境变量")
    async def set_env(self, event: AstrMessageEvent, key: str, value: str):
        '''修改环境变量：/修改环境变量 变量名 变量值'''
        try:
            # ⚠️ 实际API端点请查阅Apifox文档确认
            result = await self._call_api("/env/update", data={"key": key, "value": value})
            if result.get("code") == 0:
                yield event.plain_result(f"✅ 环境变量 {key} 已更新为 {value}")
            else:
                yield event.plain_result(f"❌ 修改失败：{result.get('msg', '未知错误')}")
        except Exception as e:
            logger.error(f"调用呆呆面板API失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")
