import aiohttp
import time
import json
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

        # --- 手动注册环境变量指令（绕过装饰器兼容性问题） ---
        self.context.register_command(
            name="envlist",
            handler=self._env_list_handler,
            description="获取环境变量列表"
        )
        self.context.register_command(
            name="环境变量列表",
            handler=self._env_list_handler,
            description="获取环境变量列表"
        )
        self.context.register_command(
            name="变量列表",
            handler=self._env_list_handler,
            description="获取环境变量列表"
        )
        self.context.register_command(
            name="变量",
            handler=self._env_list_handler,
            description="获取环境变量列表"
        )
        self.context.register_command(
            name="envs",
            handler=self._env_list_handler,
            description="获取环境变量列表"
        )
        logger.info("✅ 呆呆面板插件已加载，环境变量指令已手动注册")

    # ---------- Token 管理 ----------
    async def _get_token(self):
        # ... 保持不变，和您现有的一样 ...

    async def _call_api(self, endpoint: str, method: str = "POST", data: dict = None):
        # ... 保持不变 ...

    # ---------- 环境变量列表处理器 ----------
    async def _env_list_handler(self, event: AstrMessageEvent):
        '''实际处理函数'''
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
                    group = env.get("group", "默认分组")
                    remarks = env.get("remarks", "")
                    remarks_str = f" ({remarks})" if remarks else ""
                    display_value = value if len(value) <= 50 else value[:50] + "..."
                    msg += f"- ID: {env.get('id')} | {name} = {display_value} | 分组: {group}{remarks_str}\n"
                yield event.plain_result(msg)
        except Exception as e:
            logger.error(f"获取环境变量列表失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    # ---------- 其他指令（保留装饰器方式） ----------
    @filter.command("更新环境变量")
    async def update_env(self, event: AstrMessageEvent, *args):
        # ... 保持不变 ...

    @filter.command("运行脚本")
    async def run_script(self, event: AstrMessageEvent, script_path: str):
        # ... 保持不变 ...

    @filter.command("运行任务")
    async def run_task(self, event: AstrMessageEvent, task_name: str):
        # ... 保持不变 ...
