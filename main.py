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

        # ---------- 新增：管理员QQ配置 ----------
        admin_qq = config.get("admin_qq", None)
        if admin_qq:
            if isinstance(admin_qq, str):
                self.admin_qqs = [admin_qq]
            elif isinstance(admin_qq, list):
                self.admin_qqs = admin_qq
            else:
                self.admin_qqs = []
        else:
            self.admin_qqs = []
        if self.admin_qqs:
            logger.info(f"✅ 管理员QQ已配置：{', '.join(self.admin_qqs)}")
        else:
            logger.info("ℹ️ 未配置管理员QQ，所有用户均可使用命令（建议配置）")
        # ------------------------------------------

        logger.info("✅ 呆呆面板插件已加载（修复token地址）")

    # ---------- 新增：权限检查辅助方法 ----------
    async def _is_admin(self, event: AstrMessageEvent) -> bool:
        """检查发送者是否为管理员，若无配置则返回True"""
        if not self.admin_qqs:
            return True
        sender = str(event.get_sender_id())  # 或 event.sender_id
        return sender in self.admin_qqs
    # --------------------------------------------

    # ---------- 其余方法保持不变 ----------
    # ...（_get_token, _call_api, _fetch_env_list, _get_env_id_by_name, _create_env, _update_env, _update_env_accounts, _set_env）

    # ---------- 所有命令均添加权限检查 ----------
    @filter.command("envlist")
    async def envlist(self, event: AstrMessageEvent):
        """查看呆呆面板中的所有环境变量列表"""
        if not await self._is_admin(event):
            yield event.plain_result("⚠️ 您没有权限使用此命令。")
            return
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

    # 同样为其他命令添加相同的检查（略，实际代码中每个命令开头都需添加）
