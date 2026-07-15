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

    async def _call_api(self, endpoint: str, method: str = "POST", data: dict = None, prefix: str = "api"):
        """
        通用 API 调用，自动添加 Authorization
        prefix: "ai" -> /ai, "apiv1" -> /api/v1, "api" -> /api
        """
        token = await self._get_token()
        if prefix == "ai":
            base = self.base_url.replace("/api/v1", "") + "/ai"
        elif prefix == "apiv1":
            base = self.base_url  # /api/v1
        else:  # "api"
            base = self.base_url.replace("/api/v1", "") + "/api"
        url = f"{base}/{endpoint.lstrip('/')}"
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
                    return await self._call_api(endpoint, method, data, prefix)
                return await resp.json()

    async def _get_task_id_by_name(self, task_name: str) -> int:
        """根据任务名称获取任务 ID（精确匹配），尝试多个端点"""
        endpoints = [
            ("tasks?page=1&page_size=100", "ai"),
            ("tasks?page=1&page_size=100", "api"),
            ("tasks?page=1&page_size=100", "apiv1"),
        ]
        for endpoint, prefix in endpoints:
            try:
                result = await self._call_api(endpoint, method="GET", prefix=prefix)
                logger.info(f"尝试 {prefix} 端点，响应: {result}")
                # 提取 tasks 列表
                tasks = result.get("data")
                if tasks is None:
                    # 可能数据在 data 的 items 或 list 中
                    if isinstance(result.get("data"), dict):
                        tasks = result["data"].get("items") or result["data"].get("list")
                if tasks and isinstance(tasks, list) and len(tasks) > 0:
                    for task in tasks:
                        if task.get("name") == task_name:
                            return task.get("id")
                    # 如果列表存在但未匹配，继续下一个端点
                    continue
            except Exception as e:
                logger.warning(f"尝试 {prefix} 端点失败: {e}")
                continue
        raise Exception(f"在所有端点中均未找到名称为 '{task_name}' 的任务")

    @filter.command("运行脚本")
    async def run_script(self, event: AstrMessageEvent, script_path: str):
        '''运行呆呆面板中的脚本：/运行脚本 脚本路径（如 /root/test.sh）'''
        try:
            payload = {"path": script_path}
            result = await self._call_api("scripts/run", data=payload, prefix="apiv1")
            logger.info(f"运行脚本响应: {result}")

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
        '''运行呆呆面板中的定时任务：/运行任务 任务名称（如 "酷我验证码处理"）'''
        try:
            task_id = await self._get_task_id_by_name(task_name)
            logger.info(f"任务 '{task_name}' 对应的 ID 为 {task_id}")

            result = await self._call_api(f"tasks/{task_id}/run", method="PUT", data={}, prefix="ai")
            logger.info(f"运行任务响应: {result}")

            if result.get("error") or result.get("code") not in [0, None, ""] or result.get("status") == "error":
                error_msg = result.get("msg") or result.get("message") or result.get("error") or str(result)
                yield event.plain_result(f"❌ 运行任务失败：{error_msg}")
            else:
                yield event.plain_result(f"✅ 任务 '{task_name}' 已成功运行！")
        except Exception as e:
            logger.error(f"调用呆呆面板API失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")
