import aiohttp
import time
from urllib.parse import urljoin
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

    async def _call_api(self, endpoint: str, method: str = "POST", data: dict = None, prefix: str = "apiv1"):
        """通用 API 调用，自动添加 Authorization，正确处理 URL 拼接"""
        token = await self._get_token()
        # 构建基础 URL
        if prefix == "ai":
            # 去掉 /api/v1 或 /api，然后拼接 /ai
            base = self.base_url.replace("/api/v1", "").replace("/api", "").rstrip('/') + "/ai"
        else:
            base = self.base_url.rstrip('/')
        # 使用 urljoin 确保正确拼接，避免双斜杠
        url = urljoin(base + '/', endpoint.lstrip('/'))
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
                # 如果返回 401，重新获取 token 并重试
                if resp.status == 401:
                    self.token = None
                    self.token_expiry = 0
                    return await self._call_api(endpoint, method, data, prefix)
                # 尝试解析 JSON，失败则封装为错误
                try:
                    return await resp.json()
                except:
                    # 非 JSON 响应，封装为错误对象
                    return {"error": f"HTTP {resp.status}", "detail": response_text}

    async def _get_task_id_by_name(self, task_name: str) -> int:
        result = await self._call_api("tasks?page=1&page_size=100", method="GET", prefix="apiv1")
        tasks = result.get("data")
        if not tasks or not isinstance(tasks, list):
            raise Exception("获取任务列表失败，响应格式异常")
        for task in tasks:
            if task.get("name") == task_name:
                return task.get("id")
        raise Exception(f"未找到名称为 '{task_name}' 的任务")

    async def _get_env_id_by_name(self, env_name: str) -> int:
        result = await self._call_api("envs?page=1&page_size=100", method="GET", prefix="apiv1")
        envs = result.get("data")
        if not envs or not isinstance(envs, list):
            raise Exception("获取环境变量列表失败，响应格式异常")
        for env in envs:
            if env.get("name") == env_name:
                return env.get("id")
        raise Exception(f"未找到名称为 '{env_name}' 的环境变量")

    @filter.command("运行脚本")
    async def run_script(self, event: AstrMessageEvent, script_path: str):
        try:
            payload = {"path": script_path}
            result = await self._call_api("scripts/run", data=payload, prefix="apiv1")
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
            task_id = await self._get_task_id_by_name(task_name)
            logger.info(f"任务 '{task_name}' 对应的 ID 为 {task_id}")

            # 先尝试 PUT
            result = await self._call_api(f"tasks/{task_id}/run", method="PUT", data={}, prefix="ai")
            # 如果 405，尝试 POST
            if result.get("error") and "405" in str(result.get("error", "")):
                logger.info("PUT 返回 405，尝试 POST")
                result = await self._call_api(f"tasks/{task_id}/run", method="POST", data={}, prefix="ai")

            if result.get("error") or result.get("code") not in [0, None, ""] or result.get("status") == "error":
                error_msg = result.get("msg") or result.get("message") or result.get("error") or str(result)
                yield event.plain_result(f"❌ 运行任务失败：{error_msg}")
            else:
                yield event.plain_result(f"✅ 任务 '{task_name}' 已成功运行！")
        except Exception as e:
            logger.error(f"调用呆呆面板API失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    @filter.command("环境变量列表")
    @filter.command("变量列表")
    @filter.command("env列表")
    @filter.command("envs")
    @filter.command("变量")
    async def list_envs(self, event: AstrMessageEvent):
        try:
            result = await self._call_api("envs?page=1&page_size=100", method="GET", prefix="apiv1")
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
                    msg += f"- ID: {env.get('id')} | {name} = {value} | 分组: {group}{remarks_str}\n"
                yield event.plain_result(msg)
        except Exception as e:
            logger.error(f"获取环境变量列表失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    @filter.command("修改环境变量")
    async def update_env(self, event: AstrMessageEvent, env_name: str, new_value: str):
        try:
            env_id = await self._get_env_id_by_name(env_name)
            payload = {"name": env_name, "value": new_value}
            result = await self._call_api(f"envs/{env_id}", method="PUT", data=payload, prefix="apiv1")
            if result.get("error") or result.get("code") not in [0, None, ""] or result.get("status") == "error":
                error_msg = result.get("msg") or result.get("message") or result.get("error") or str(result)
                yield event.plain_result(f"❌ 修改失败：{error_msg}")
            else:
                yield event.plain_result(f"✅ 环境变量 '{env_name}' 已成功更新为 '{new_value}'！")
        except Exception as e:
            logger.error(f"修改环境变量失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")
