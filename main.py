import aiohttp
import time
import json
import html
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
        logger.info("✅ 呆呆面板插件已加载（最终调试版）")

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
                    return {"error": f"HTTP {resp.status}", "detail": response_text}

    # ---------- 公共函数 ----------
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

    # ---------- 批量更新账户 ----------
    async def _update_env_accounts(self, env_name: str, accounts: dict) -> str:
        env_id = await self._get_env_id_by_name(env_name)
        if env_id is None:
            items = [f"{acc}#{val}" for acc, val in accounts.items()]
            initial = '&'.join(items)
            if await self._create_env(env_name, initial):
                return f"✅ 环境变量 '{env_name}' 已创建"
            else:
                return f"❌ 创建环境变量 '{env_name}' 失败"

        envs = await self._fetch_env_list()
        current_value = None
        for env in envs:
            if env.get("id") == env_id:
                current_value = env.get("value", "")
                break
        if current_value is None:
            return "❌ 未找到该环境变量的当前值"

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
                return f"❌ 当前值不是账号格式，请使用覆盖模式：/更新环境变量 {env_name} <新值>"
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
            return f"✅ 环境变量 '{env_name}' 已更新"
        else:
            return "❌ 更新失败"

    # ---------- 覆盖模式 ----------
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

    # ========== 指令部分 ==========
    # 环境变量列表（保持之前，此处省略，与之前一致，为简洁不重复粘贴，实际需保留所有列表指令）

    # ---------- 更新环境变量（最终版，带详尽解析） ----------
    @filter.command("更新环境变量")
    async def update_env(self, event: AstrMessageEvent, env_name: str, new_value: str):
        '''
        用法：
        覆盖模式：/更新环境变量 <变量名> <新值>（不包含#）
        账户更新模式：
          - 单账户：/更新环境变量 <变量名> <账号#新值>
          - 多账户：/更新环境变量 <变量名> <账号1#值1&账号2#值2&...>
        '''
        try:
            # 记录原始输入
            logger.info(f"原始输入 env_name: {env_name}")
            logger.info(f"原始输入 new_value: {new_value} (repr: {repr(new_value)})")
            # 解码 HTML 实体（如 &amp; -> &）
            decoded = html.unescape(new_value)
            logger.info(f"HTML 解码后: {decoded}")
            # 去除可能的换行和首尾空格
            raw = decoded.replace('\n', '').replace('\r', '').strip()
            logger.info(f"清洗后: {raw}")

            # 尝试多种分隔符
            # 1. 如果包含 &，按 & 分割
            if '&' in raw:
                parts = raw.split('&')
                accounts = {}
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    if '#' in part:
                        acc_val = part.split('#', 1)
                        acc = acc_val[0].strip()
                        val = acc_val[1].strip() if len(acc_val) > 1 else ''
                        if acc and val:
                            accounts[acc] = val
                        else:
                            yield event.plain_result(f"❌ 格式错误：'{part}' 缺少账号或值")
                            return
                    else:
                        yield event.plain_result(f"❌ 格式错误：'{part}' 缺少 # 分隔符")
                        return
                if accounts:
                    msg = await self._update_env_accounts(env_name, accounts)
                    if "✅" in msg:
                        yield event.plain_result(f"检测到 {len(accounts)} 个账户，{msg}")
                    else:
                        yield event.plain_result(msg)
                else:
                    yield event.plain_result("❌ 未检测到有效的账户更新条目")
                return

            # 2. 如果不含 &，但包含空格，可能多个账号用空格分隔（例如 "15507099836#12748 18870799391#35136"）
            if ' ' in raw and '#' in raw:
                parts = raw.split()
                accounts = {}
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    if '#' in part:
                        acc_val = part.split('#', 1)
                        acc = acc_val[0].strip()
                        val = acc_val[1].strip() if len(acc_val) > 1 else ''
                        if acc and val:
                            accounts[acc] = val
                        else:
                            yield event.plain_result(f"❌ 格式错误：'{part}' 缺少账号或值")
                            return
                    else:
                        yield event.plain_result(f"❌ 格式错误：'{part}' 缺少 # 分隔符")
                        return
                if accounts:
                    msg = await self._update_env_accounts(env_name, accounts)
                    if "✅" in msg:
                        yield event.plain_result(f"检测到 {len(accounts)} 个账户，{msg}")
                    else:
                        yield event.plain_result(msg)
                else:
                    yield event.plain_result("❌ 未检测到有效的账户更新条目")
                return

            # 3. 不包含任何分隔符，可能是单账户或覆盖
            if '#' in raw:
                acc_val = raw.split('#', 1)
                acc = acc_val[0].strip()
                val = acc_val[1].strip() if len(acc_val) > 1 else ''
                if acc and val:
                    msg = await self._update_env_accounts(env_name, {acc: val})
                    if "✅" in msg:
                        yield event.plain_result(f"检测到 1 个账户，{msg}")
                    else:
                        yield event.plain_result(msg)
                else:
                    # 格式不完整，覆盖
                    msg = await self._set_env(env_name, raw)
                    yield event.plain_result(msg)
            else:
                # 完全不含 #，覆盖
                msg = await self._set_env(env_name, raw)
                yield event.plain_result(msg)
        except Exception as e:
            logger.error(f"更新环境变量失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")

    # 其他指令（运行脚本、运行任务、环境变量列表）与之前相同，此处省略，实际使用需保留所有。
