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

    # ---------- Token 管理 ----------
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

    # ---------- 通用 API 调用 ----------
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
                    # 非 JSON 响应，封装为错误
                    return {"error": f"HTTP {resp.status}", "detail": response_text}

    # ---------- 辅助：根据名称获取环境变量 ID ----------
    async def _get_env_id_by_name(self, env_name: str) -> int:
        """返回环境变量 ID，如果不存在返回 None"""
        result = await self._call_api("envs?page=1&page_size=100", method="GET")
        envs = result.get("data")
        if not envs or not isinstance(envs, list):
            return None
        for env in envs:
            if env.get("name") == env_name:
                return env.get("id")
        return None

    # ---------- 辅助：创建环境变量 ----------
    async def _create_env(self, name: str, value: str, group: str = "默认分组") -> bool:
        """创建新环境变量，成功返回 True，失败返回 False"""
        payload = {
            "name": name,
            "value": value,
            "group": group
        }
        result = await self._call_api("envs", method="POST", data=payload)
        if result.get("error") or result.get("code") not in [0, None, ""]:
            logger.error(f"创建环境变量失败: {result}")
            return False
        return True

    # ---------- 辅助：更新环境变量 ----------
    async def _update_env(self, env_id: int, name: str, value: str) -> bool:
        """更新已有环境变量，成功返回 True"""
        payload = {"name": name, "value": value}
        result = await self._call_api(f"envs/{env_id}", method="PUT", data=payload)
        if result.get("error") or result.get("code") not in [0, None, ""]:
            logger.error(f"更新环境变量失败: {result}")
            return False
        return True

    # ---------- 覆盖模式：直接设置环境变量 ----------
    async def _set_env(self, env_name: str, new_value: str, event):
        env_id = await self._get_env_id_by_name(env_name)
        if env_id is None:
            # 不存在，创建
            if await self._create_env(env_name, new_value):
                yield event.plain_result(f"✅ 环境变量 '{env_name}' 已创建，值为 '{new_value}'")
            else:
                yield event.plain_result(f"❌ 创建环境变量 '{env_name}' 失败，请检查权限或API")
        else:
            if await self._update_env(env_id, env_name, new_value):
                yield event.plain_result(f"✅ 环境变量 '{env_name}' 已更新为 '{new_value}'")
            else:
                yield event.plain_result(f"❌ 更新环境变量 '{env_name}' 失败，请检查权限或API")

    # ---------- 账户更新模式：更新 JSON 对象中的指定键 ----------
    async def _update_env_account(self, env_name: str, account: str, new_value: str, event):
        env_id = await self._get_env_id_by_name(env_name)
        if env_id is None:
            # 不存在，创建初始 JSON
            initial = {account: new_value}
            json_str = json.dumps(initial, ensure_ascii=False)
            if await self._create_env(env_name, json_str):
                yield event.plain_result(f"✅ 环境变量 '{env_name}' 已创建，账户 '{account}' 设为 '{new_value}'")
            else:
                yield event.plain_result(f"❌ 创建环境变量 '{env_name}' 失败，请检查权限或API")
            return

        # 存在，获取当前值
        result = await self._call_api("envs?page=1&page_size=100", method="GET")
        envs = result.get("data")
        if not envs:
            yield event.plain_result("❌ 获取环境变量列表失败，无法读取当前值")
            return
        current_value = None
        for env in envs:
            if env.get("id") == env_id:
                current_value = env.get("value", "")
                break
        if current_value is None:
            yield event.plain_result("❌ 未找到该环境变量的当前值")
            return

        # 尝试解析 JSON
        try:
            data = json.loads(current_value) if current_value.strip() else {}
        except json.JSONDecodeError:
            # 当前值不是 JSON，无法更新账户，提示用户使用覆盖模式
            yield event.plain_result(f"❌ 当前环境变量 '{env_name}' 的值不是 JSON 格式，无法按账户更新。请使用覆盖模式：/更新环境变量 {env_name} <新值>")
            return

        if not isinstance(data, dict):
            yield event.plain_result(f"❌ 当前环境变量 '{env_name}' 的值不是对象格式，无法按账户更新")
            return

        # 更新指定账户
        data[account] = new_value
        new_json_str = json.dumps(data, ensure_ascii=False)
        if await self._update_env(env_id, env_name, new_json_str):
            yield event.plain_result(f"✅ 环境变量 '{env_name}' 中账户 '{account}' 已更新为 '{new_value}'，其他账户保持不变")
        else:
            yield event.plain_result(f"❌ 更新环境变量 '{env_name}' 失败，请检查权限或API")

    # ---------- 指令：更新环境变量（支持两种模式） ----------
    @filter.command("更新环境变量")
    async def update_env(self, event: AstrMessageEvent, *args):
        '''
        用法：
        /更新环境变量 <变量名> <新值>                  → 覆盖整个变量
        /更新环境变量 <变量名> <账户名> <新值>        → 更新 JSON 对象中的指定账户（其他不变）
        '''
        if len(args) < 2:
            yield event.plain_result(
                "❌ 用法：\n"
                "  覆盖模式：/更新环境变量 <变量名> <新值>\n"
                "  账户更新模式：/更新环境变量 <变量名> <账户名> <新值>"
            )
            return
        env_name = args[0]
        if len(args) == 2:
            # 覆盖模式
            await self._set_env(env_name, args[1], event)
        elif len(args) == 3:
            # 账户更新模式
            await self._update_env_account(env_name, args[1], args[2], event)
        else:
            yield event.plain_result("❌ 参数过多，请检查格式。")

    # ---------- 以下为原有指令 ----------
    @filter.command("运行脚本")
    async def run_script(self, event: AstrMessageEvent, script_path: str):
        '''运行呆呆面板中的脚本：/运行脚本 脚本路径（如 /root/test.sh）'''
        try:
            payload = {"path": script_path}
            result = await self._call_api("scripts/run", data=payload)
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
            # 获取任务 ID
            result = await self._call_api("tasks?page=1&page_size=100", method="GET")
            tasks = result.get("data")
            if not tasks or not isinstance(tasks, list):
                yield event.plain_result("❌ 获取任务列表失败，请检查网络或权限")
                return
            task_id = None
            for task in tasks:
                if task.get("name") == task_name:
                    task_id = task.get("id")
                    break
            if task_id is None:
                yield event.plain_result(f"❌ 未找到名称为 '{task_name}' 的任务")
                return

            logger.info(f"任务 '{task_name}' 对应的 ID 为 {task_id}")
            result = await self._call_api(f"tasks/{task_id}/run", method="PUT", data={})
            logger.info(f"运行任务响应: {result}")

            if result.get("error") or result.get("code") not in [0, None, ""] or result.get("status") == "error":
                error_msg = result.get("msg") or result.get("message") or result.get("error") or str(result)
                yield event.plain_result(f"❌ 运行任务失败：{error_msg}")
            else:
                message = result.get("message", "任务已启动")
                yield event.plain_result(f"✅ {message}")
        except Exception as e:
            logger.error(f"调用呆呆面板API失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    # 可选：增加环境变量列表指令（方便查看）
    @filter.command("环境变量列表")
    @filter.command("变量列表")
    @filter.command("env列表")
    @filter.command("envs")
    @filter.command("变量")
    async def list_envs(self, event: AstrMessageEvent):
        '''查看所有环境变量：/环境变量列表 或 /变量 等'''
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
                    # 如果值太长，截断显示
                    display_value = value if len(value) <= 50 else value[:50] + "..."
                    msg += f"- ID: {env.get('id')} | {name} = {display_value} | 分组: {group}{remarks_str}\n"
                yield event.plain_result(msg)
        except Exception as e:
            logger.error(f"获取环境变量列表失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")
