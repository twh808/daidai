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
        logger.info("✅ 呆呆面板插件已加载（终极版）")

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
                    raise Exception(f"Token 响应中未找到 access_token")
                expires_in = result.get("data", {}).get("expires_in", 86400)
                self.token_expiry = time.time() + expires_in - 60
                self.token = token
                return token

    async def _call_api(self, endpoint: str, method: str = "POST", data: dict = None):
        token = await self._get_token()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
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

    async def _fetch_env_list(self):
        result = await self._call_api("envs?page=1&page_size=100", method="GET")
        return result.get("data", [])

    async def _get_env_id_by_name(self, name: str):
        envs = await self._fetch_env_list()
        for env in envs:
            if env.get("name") == name:
                return env.get("id")
        return None

    async def _update_env_value(self, env_id: int, name: str, value: str):
        return await self._call_api(f"envs/{env_id}", method="PUT", data={"name": name, "value": value})

    async def _create_env(self, name: str, value: str):
        return await self._call_api("envs", method="POST", data={"name": name, "value": value})

    # ========== 指令 ==========
    @filter.command("envlist")
    @filter.command("envs")
    @filter.command("环境变量列表")
    @filter.command("变量列表")
    @filter.command("变量")
    async def list_envs(self, event: AstrMessageEvent):
        try:
            envs = await self._fetch_env_list()
            if not envs:
                yield event.plain_result("📭 当前没有环境变量")
            else:
                msg = "📋 环境变量列表：\n"
                for env in envs:
                    name = env.get("name", "未命名")
                    value = env.get("value", "")
                    group = env.get("group", "默认分组")
                    display_value = value if len(value) <= 50 else value[:50] + "..."
                    msg += f"- {name} = {display_value} (分组: {group})\n"
                yield event.plain_result(msg)
        except Exception as e:
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    @filter.command("updateenv")
    @filter.command("更新环境变量")
    async def update_env(self, event: AstrMessageEvent, env_name: str, new_value: str):
        try:
            env_id = await self._get_env_id_by_name(env_name)
            if env_id is None:
                result = await self._create_env(env_name, new_value)
                if result.get("error"):
                    yield event.plain_result(f"❌ 创建失败：{result}")
                else:
                    yield event.plain_result(f"✅ 环境变量 '{env_name}' 已创建")
            else:
                result = await self._update_env_value(env_id, env_name, new_value)
                if result.get("error"):
                    yield event.plain_result(f"❌ 更新失败：{result}")
                else:
                    yield event.plain_result(f"✅ 环境变量 '{env_name}' 已更新")
        except Exception as e:
            yield event.plain_result(f"❌ 失败：{str(e)}")

    @filter.command("runtask")
    @filter.command("运行任务")
    async def run_task(self, event: AstrMessageEvent, task_name: str):
        try:
            result = await self._call_api("tasks?page=1&page_size=100", method="GET")
            tasks = result.get("data")
            if not tasks:
                yield event.plain_result("❌ 获取任务列表失败")
                return
            task_id = None
            for task in tasks:
                if task.get("name") == task_name:
                    task_id = task.get("id")
                    break
            if task_id is None:
                yield event.plain_result(f"❌ 未找到任务：{task_name}")
                return
            result = await self._call_api(f"tasks/{task_id}/run", method="PUT", data={})
            if result.get("error"):
                yield event.plain_result(f"❌ 运行失败：{result}")
            else:
                yield event.plain_result(f"✅ 任务 '{task_name}' 已运行")
        except Exception as e:
            yield event.plain_result(f"❌ 失败：{str(e)}")

    @filter.command("runscript")
    @filter.command("运行脚本")
    async def run_script(self, event: AstrMessageEvent, script_path: str):
        try:
            result = await self._call_api("scripts/run", method="POST", data={"path": script_path})
            if result.get("error"):
                yield event.plain_result(f"❌ 运行失败：{result}")
            else:
                yield event.plain_result(f"✅ 脚本已执行")
        except Exception as e:
            yield event.plain_result(f"❌ 失败：{str(e)}")
