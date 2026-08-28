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
        self.base_url = config.get("base_url", "http://127.0.0.1:5700/api/v1")
        self.app_key = config.get("app_key", "")
        self.app_secret = config.get("app_secret", "")
        self.token = None
        self.token_expiry = 0

        admin_str = config.get("admin_qq", "").strip()
        self.admin_qqs = [qq.strip() for qq in admin_str.split(',') if qq.strip()]
        if self.admin_qqs:
            logger.info(f"✅ 呆呆面板管理 - 管理员已配置: {self.admin_qqs}")
        else:
            logger.info("ℹ️ 呆呆面板管理 - 未配置管理员，所有用户均可使用")

        logger.info("✅ 呆呆面板插件已加载（无斜杠交互版）")

    # ---------- 权限检查 ----------
    def _is_admin(self, event: AstrMessageEvent) -> bool:
        if not self.admin_qqs:
            return True
        try:
            sender = str(event.get_sender_id())
        except:
            sender = str(event.get_user_id()) if hasattr(event, 'get_user_id') else "unknown"
        return sender in self.admin_qqs

    # ---------- Token & API ----------
    async def _get_token(self):
        if self.token and self.token_expiry > time.time():
            return self.token
        base = self.base_url.replace("/api/v1", "").replace("/api", "")
        token_url = f"{base}/api/open-api/token"
        payload = {"app_key": self.app_key, "app_secret": self.app_secret}
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"获取 Token 失败，状态码：{resp.status}，响应：{error_text}")
                result = await resp.json()
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
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                if resp.status == 401:
                    self.token = None
                    self.token_expiry = 0
                    return await self._call_api(endpoint, method, data)
                try:
                    return await resp.json()
                except:
                    return {"error": f"HTTP {resp.status}", "detail": response_text}

    # ---------- 环境变量核心函数 ----------
    async def _fetch_env_list(self):
        result = await self._call_api("envs?page=1&page_size=100", method="GET")
        return result.get("data", [])

    async def _get_env_id_by_name(self, env_name: str) -> int:
        envs = await self._fetch_env_list()
        for env in envs:
            if env.get("name") == env_name:
                return env.get("id")
        return None

    async def _create_env(self, name: str, value: str, group: str = "默认分组") -> bool:
        payload = {"name": name, "value": value, "group": group}
        result = await self._call_api("envs", method="POST", data=payload)
        if result.get("error") or result.get("code") not in [0, None, ""]:
            logger.error(f"创建环境变量失败: {result}")
            return False
        return True

    async def _update_env(self, env_id: int, name: str, value: str) -> bool:
        payload = {"name": name, "value": value}
        result = await self._call_api(f"envs/{env_id}", method="PUT", data=payload)
        if result.get("error") or result.get("code") not in [0, None, ""]:
            logger.error(f"更新环境变量失败: {result}")
            return False
        return True

    async def _update_env_accounts(self, env_name: str, accounts: dict) -> tuple:
        total = len(accounts)
        env_id = await self._get_env_id_by_name(env_name)
        if env_id is None:
            items = [f"{acc}#{val}" for acc, val in accounts.items()]
            initial = '&'.join(items)
            if await self._create_env(env_name, initial):
                return (f"✅ 环境变量 '{env_name}' 已创建", total)
            else:
                return (f"❌ 创建环境变量 '{env_name}' 失败", total)

        envs = await self._fetch_env_list()
        current_value = None
        for env in envs:
            if env.get("id") == env_id:
                current_value = env.get("value", "")
                break
        if current_value is None:
            return ("❌ 未找到该环境变量的当前值", total)

        if '\n' in current_value:
            separator = '\n'
        elif '&' in current_value:
            separator = '&'
        else:
            separator = None

        if separator is None:
            if '#' in current_value:
                parts = current_value.split('#', 1)
                existing_acc = parts[0]
                items = []
                if existing_acc in accounts:
                    items.append(f"{existing_acc}#{accounts[existing_acc]}")
                    accounts.pop(existing_acc)
                else:
                    items.append(current_value)
                for acc, val in accounts.items():
                    items.append(f"{acc}#{val}")
                new_val = '&'.join(items)
            else:
                return ("❌ 当前值不是账号格式，请使用覆盖模式", total)
        else:
            items = current_value.split(separator)
            items = [item for item in items if item.strip()]
            new_items = []
            for item in items:
                if '#' in item:
                    acc, val = item.split('#', 1)
                    if acc in accounts:
                        new_items.append(f"{acc}#{accounts[acc]}")
                        accounts.pop(acc)
                    else:
                        new_items.append(item)
                else:
                    new_items.append(item)
            for acc, val in accounts.items():
                new_items.append(f"{acc}#{val}")
            new_val = separator.join(new_items)

        if await self._update_env(env_id, env_name, new_val):
            return (f"✅ 环境变量 '{env_name}' 已更新", total)
        else:
            return ("❌ 更新失败", total)

    async def _set_env(self, env_name: str, new_value: str) -> str:
        env_id = await self._get_env_id_by_name(env_name)
        if env_id is None:
            if await self._create_env(env_name, new_value):
                return f"✅ 环境变量 '{env_name}' 已创建，值为 '{new_value}'"
            else:
                return f"❌ 创建环境变量 '{env_name}' 失败"
        else:
            if await self._update_env(env_id, env_name, new_value):
                return f"✅ 环境变量 '{env_name}' 已更新为 '{new_value}'"
            else:
                return f"❌ 更新环境变量 '{env_name}' 失败"

    # ---------- 帮助菜单 ----------
    def _get_help_text(self) -> str:
        return """🤖 **呆呆面板管理插件帮助**

发送以下命令（无需斜杠）进行操作：

**环境变量管理：**
  - `呆呆 环境变量 列表` – 查看所有变量
  - `呆呆 更新变量 <变量名> <账号#值>` – 更新单账号
  - `呆呆 更新变量 <变量名>`（换行输入多个账号） – 批量更新，每行一个 `账号#值`
  - `呆呆 覆盖变量 <变量名> <新值>` – 覆盖整个变量值

**脚本管理：**
  - `呆呆 运行脚本 <脚本绝对路径>` – 执行指定脚本

**任务管理：**
  - `呆呆 运行任务 <任务名称>` – 运行指定定时任务

💡 **示例：**
  - `呆呆 环境变量 列表`
  - `呆呆 更新变量 CODE 13800138000#123456`
  - 批量更新：
    ```
    呆呆 更新变量 CODE
    账号1#值1
    账号2#值2
    ```
  - `呆呆 运行脚本 /data/scripts/cleanup.sh`

⚠️ 只有管理员QQ可使用所有命令。"""

    # ========== 纯文本入口：发送“呆呆管理”唤出菜单 ==========
    @filter.message(关键字="呆呆管理")
    async def daidai_menu(self, event: AstrMessageEvent):
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 您没有权限使用此命令。")
            return
        yield event.plain_result(self._get_help_text())

    # ========== 统一消息处理器：解析以“呆呆”开头的命令 ==========
    @filter.message()
    async def daidai_command_handler(self, event: AstrMessageEvent):
        message = event.message_str.strip()
        if not message.startswith("呆呆 "):
            return

        if not self._is_admin(event):
            yield event.plain_result("⚠️ 您没有权限使用此命令。")
            return

        content = message[3:].strip()
        if not content:
            yield event.plain_result("❌ 请输入子命令，例如：呆呆 环境变量 列表")
            return

        first_space = content.find(' ')
        if first_space == -1:
            cmd = content
            args = ""
        else:
            cmd = content[:first_space]
            args = content[first_space+1:].strip()

        if cmd == "环境变量" and args.startswith("列表"):
            await self._list_envs(event)
        elif cmd == "更新变量":
            if not args:
                yield event.plain_result("❌ 请指定变量名，例如：呆呆 更新变量 CODE 账号#值")
                return
            second_space = args.find(' ')
            if second_space == -1:
                yield event.plain_result("❌ 请提供账号#值，例如：呆呆 更新变量 CODE 13800138000#123456")
                return
            env_name = args[:second_space]
            new_value = args[second_space+1:].strip()
            if not new_value:
                yield event.plain_result("❌ 请提供账号#值")
                return
            await self._update_env_cmd(event, env_name, new_value)
        elif cmd == "覆盖变量":
            if not args:
                yield event.plain_result("❌ 请指定变量名和新值")
                return
            second_space = args.find(' ')
            if second_space == -1:
                yield event.plain_result("❌ 请提供新值")
                return
            env_name = args[:second_space]
            new_value = args[second_space+1:].strip()
            await self._set_env_cmd(event, env_name, new_value)
        elif cmd == "运行脚本":
            if not args:
                yield event.plain_result("❌ 请指定脚本路径")
                return
            await self._run_script_cmd(event, args)
        elif cmd == "运行任务":
            if not args:
                yield event.plain_result("❌ 请指定任务名称")
                return
            await self._run_task_cmd(event, args)
        else:
            yield event.plain_result(f"❌ 未知命令。发送 `呆呆管理` 查看帮助。")

    # ---------- 具体命令实现 ----------
    async def _list_envs(self, event: AstrMessageEvent):
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
                    remarks = env.get("remarks", "")
                    remarks_str = f" ({remarks})" if remarks else ""
                    display_value = value if len(value) <= 50 else value[:50] + "..."
                    msg += f"- ID: {env.get('id')} | {name} = {display_value} | 分组: {group}{remarks_str}\n"
                yield event.plain_result(msg)
        except Exception as e:
            logger.error(f"获取环境变量列表失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    async def _update_env_cmd(self, event: AstrMessageEvent, env_name: str, new_value: str):
        try:
            raw = new_value.replace('\r', '').strip()
            lines = [line.strip() for line in raw.split('\n') if line.strip()]
            accounts = {}
            if len(lines) > 1:
                for line in lines:
                    if '#' in line:
                        acc, val = line.split('#', 1)
                        acc = acc.strip()
                        val = val.strip()
                        if acc and val:
                            accounts[acc] = val
                        else:
                            yield event.plain_result(f"❌ 格式错误：'{line}' 缺少账号或值")
                            return
                    else:
                        yield event.plain_result(f"❌ 格式错误：'{line}' 缺少 # 分隔符")
                        return
            else:
                single = lines[0] if lines else raw
                if '&' in single:
                    parts = single.split('&')
                    for part in parts:
                        part = part.strip()
                        if not part:
                            continue
                        if '#' in part:
                            acc, val = part.split('#', 1)
                            acc = acc.strip()
                            val = val.strip()
                            if acc and val:
                                accounts[acc] = val
                            else:
                                yield event.plain_result(f"❌ 格式错误：'{part}' 缺少账号或值")
                                return
                        else:
                            yield event.plain_result(f"❌ 格式错误：'{part}' 缺少 # 分隔符")
                            return
                else:
                    if '#' in single:
                        acc, val = single.split('#', 1)
                        acc = acc.strip()
                        val = val.strip()
                        if acc and val:
                            accounts[acc] = val
                        else:
                            yield event.plain_result(f"❌ 格式错误：'{single}' 缺少账号或值")
                            return
                    else:
                        msg = await self._set_env(env_name, single)
                        yield event.plain_result(msg)
                        return

            if accounts:
                msg, count = await self._update_env_accounts(env_name, accounts)
                if "✅" in msg:
                    yield event.plain_result(f"检测到 {count} 个账户，{msg}")
                else:
                    yield event.plain_result(msg)
            else:
                yield event.plain_result("❌ 未检测到有效的账户更新条目")
        except Exception as e:
            logger.error(f"更新环境变量失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    async def _set_env_cmd(self, event: AstrMessageEvent, env_name: str, new_value: str):
        try:
            raw = new_value.replace('\n', '').replace('\r', '').strip()
            msg = await self._set_env(env_name, raw)
            yield event.plain_result(msg)
        except Exception as e:
            logger.error(f"覆盖环境变量失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    async def _run_script_cmd(self, event: AstrMessageEvent, script_path: str):
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

    async def _run_task_cmd(self, event: AstrMessageEvent, task_name: str):
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
