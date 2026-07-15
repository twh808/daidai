import aiohttp
import jwt           # 需要安装 PyJWT：pip install PyJWT
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
        self.token = None          # 当前 token 字符串
        self.token_expiry = 0      # 过期时间戳（Unix秒）

    async def _get_token(self):
        """调用 /api/open-api/token 获取新的 Bearer Token"""
        if self.token and self.token_expiry > time.time():
            # Token 未过期，直接返回
            return self.token

        # 注意：获取 token 的接口可能不在 /api/v1 前缀下，而是直接在 /api 下
        token_url = f"http://192.168.5.1:5777/api/open-api/token"
        payload = {
            "app_key": self.app_key,
            "app_secret": self.app_secret
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, json=payload) as resp:
                if resp.status != 200:
                    raise Exception(f"获取 Token 失败，状态码：{resp.status}")
                result = await resp.json()
                # 假设返回格式为 {"code":0, "data":{"token":"..."}}
                # 或根据实际情况解析
                token = result.get("data", {}).get("token") or result.get("token")
                if not token:
                    raise Exception(f"Token 响应中未找到 token 字段：{result}")
                # 解析 JWT 获取过期时间
                try:
                    decoded = jwt.decode(token, options={"verify_signature": False})
                    self.token_expiry = decoded.get("exp", 0)
                except:
                    # 如果无法解析，设置一个较短的过期时间（如 1 小时）
                    self.token_expiry = time.time() + 3600
                self.token = token
                return token

    async def _call_api(self, endpoint: str, method: str = "POST", data: dict = None):
        """通用 API 调用，自动添加 Authorization"""
        # 获取有效 token
        token = await self._get_token()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        logger.info(f"请求 URL: {url}")
        logger.info(f"请求体: {data}")
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as resp:
                response_text = await resp.text()
                logger.info(f"响应状态码: {resp.status}")
                logger.info(f"响应内容: {response_text}")
                # 如果返回 401，可能 token 已过期，清除 token 并重试一次
                if resp.status == 401:
                    self.token = None
                    self.token_expiry = 0
                    # 递归重试一次
                    return await self._call_api(endpoint, method, data)
                return await resp.json()

    @filter.command("运行脚本")
    async def run_script(self, event: AstrMessageEvent, script_path: str):
        '''运行呆呆面板中的脚本：/运行脚本 脚本路径（如 /root/test.sh）'''
        try:
            payload = {"path": script_path}
            result = await self._call_api("/scripts/run", data=payload)
            # 根据实际响应格式调整判断逻辑
            if result.get("status") == "success" or result.get("code") == 0:
                run_id = result.get("data", {}).get("run_id")
                if run_id:
                    yield event.plain_result(f"✅ 脚本已提交运行！运行ID：{run_id}")
                else:
                    yield event.plain_result(f"✅ 运行成功，但未返回 run_id")
            else:
                error_msg = result.get("msg") or result.get("message") or "未知错误"
                yield event.plain_result(f"❌ 运行失败：{error_msg}")
        except Exception as e:
            logger.error(f"调用呆呆面板API失败: {e}")
            yield event.plain_result(f"❌ 请求失败：{str(e)}")
