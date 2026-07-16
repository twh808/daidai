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
        logger.info("✅ 呆呆面板插件已加载（纯装饰器版）")

    async def _get_token(self):
        if self.token and self.token_expiry > time.time():
            return self.token

        token_url = f"http://192.168.5.1:5777/api/open-api/token"
        payload = {
            "app_key": self.app_key,
            "app_secret": self.app_secret
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"获取 Token 失败，状态码：{resp.status}，响应：{error_text}")
                result = await resp.json()
                logger.info(f"Token 响应: {result}")

                token = result.get("data", {}).get("access_token")
                if not token:
                    raise Exception(f"Token 响应中未找到 access_token 字段：{result}")

                expires_in = result.get("data", {}).get("expires_in", 86400)
                self.token_expiry = time.time() + expires_in - 60
                self.token = token
                return token

    async def _call_api(self, endpoint: str, method: str = "POST", data: dict = None):
        token = await self._get_token()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        logger.info(f"请求 URL: {url}")
        logger.info(f"请求方法: {method}")
        logger.info(f"请求体: {data}")
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                logger.info(f"响应状态码: {resp.status}")
                logger.info(f"响应内容: {response_text}")
                if resp.status == 401:
                    self.token = None
                    self.token_expiry = 0
                    return await self._call_api(endpoint, method, data)
                try:
                    return await resp.json()
                except:
                    return {"error": f"HTTP {resp.status}", "detail": response_text}

    # ---------- 环境变量列表指令（只保留 /envlist） ----------
    @filter.command("envlist")
    async def envlist(self, event: AstrMessageEvent):
        '''获取环境变量列表：/envlist'''
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

    # ---------- 保留原有的运行脚本和运行任务指令（确保能正常工作） ----------
    @filter.command("运行脚本")
    async def run_script(self, event: AstrMessageEvent, script_path: str):
        try:
            payload = {"path": script_path}
            result = await self._call_api("scripts/run", data=payload)
            if result.get("error") or result.get("code") not in [0, None, ""] or result.get("status") == "error":
                error_msg = result.get("msg") or result.get("message") or result.get("error") or str(result)
                yield event.plain_result(f"❌ 运行失败：{error_msg}")
            else:
                yield event.plain_result(f"✅ 脚本已成功执行！")
        except Exception as e:
            logger.error(f"调用呆呆面板API失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    @filter.command("运行任务")
    async def run_task(self, event: AstrMessageEvent, task_name: str):
        try:
            result = await self._call_api("tasks?page=1&page_size=100", method="GET")
            tasks = result.get("data")
            if not tasks or not isinstance(tasks, list):
                yield event.plain_result("❌ 获取任务列表失败")
                return
            task_id = None
            for task in tasks:
                if task.get("name") == task_name:
                    task_id = task.get("id")
                    break
            if task_id is None:
                yield event.plain_result(f"❌ 未找到名称为 '{task_name}' 的任务")
                return

            result = await self._call_api(f"tasks/{task_id}/run", method="PUT", data={})
            if result.get("error") or result.get("code") not in [0, None, ""] or result.get("status") == "error":
                error_msg = result.get("msg") or result.get("message") or result.get("error") or str(result)
                yield event.plain_result(f"❌ 运行任务失败：{error_msg}")
            else:
                message = result.get("message", "任务已启动")
                yield event.plain_result(f"✅ {message}")
        except Exception as e:
            logger.error(f"调用呆呆面板API失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")
