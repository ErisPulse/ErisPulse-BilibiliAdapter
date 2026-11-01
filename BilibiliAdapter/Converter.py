"""
B 站私信事件 → OneBot12 标准事件转换

bilibili_api session 回调收到的 data 结构（fetch_session_msgs 的消息体）：
- sender_uid / receiver_id: 会话双方 UID
- content: JSON 字符串或 dict，文本为 {"content": "..."}，
  图片为 {"url": [...]} 或 {"pictures": [{"url": ...}, ...]}
- msg_type: 1=文本 2=图片 5=撤回
- timestamp / msg_key / msg_status

转换结果附带 bilibili_raw（原始 data）与 bilibili_raw_type（text/picture）。
"""
import json
import time
import uuid

__all__ = ["BilibiliConverter"]


class BilibiliConverter:
    """B 站私信事件转换器"""

    def __init__(self, platform: str = "bilibili"):
        self.platform = platform

    def convert(self, raw_event: dict, *, bot_id: str = "",
                user_name: str = "", account_id: str = "") -> dict | None:
        """
        将 bilibili_api session 事件的 data 转换为 OneBot12 消息事件

        :param raw_event: 事件 data 字典
        :param bot_id: 本账户 UID（self.user_id）
        :param user_name: 本账户昵称（self.user_name）
        :param account_id: 账户配置名（self.account_id）
        :return: OneBot12 事件字典；无法识别时返回 None
        """
        if not isinstance(raw_event, dict):
            return None
        sender_uid = str(
            raw_event.get("sender_uid") or raw_event.get("sender_id") or ""
        )
        if not sender_uid:
            return None

        raw_type, segments, alt_parts = self._parse_content(raw_event.get("content"))
        if not segments:
            return None

        self_info = {
            "platform": self.platform,
            "user_id": str(bot_id),
            "account_id": str(account_id),
        }
        if user_name:
            self_info["user_name"] = user_name

        event = {
            "id": str(raw_event.get("msg_key") or uuid.uuid4()),
            "time": self._normalize_timestamp(raw_event.get("timestamp")),
            "type": "message",
            "detail_type": "private",
            "platform": self.platform,
            "self": self_info,
            "user_id": sender_uid,
            "message": segments,
            "alt_message": " ".join(alt_parts),
            "bilibili_raw": raw_event,
            "bilibili_raw_type": raw_type,
        }
        nickname = str(raw_event.get("sender_name") or "")
        if nickname:
            event["user_nickname"] = nickname
        return event

    def _parse_content(self, content) -> tuple:
        """解析 content（JSON 字符串或 dict）为 (raw_type, segments, alt_parts)"""
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except (ValueError, TypeError):
                content = {"content": content}
        if not isinstance(content, dict):
            content = {}

        segments = []
        alt_parts = []
        raw_type = "text"

        text = str(content.get("message") or content.get("content") or "")
        if text:
            segments.append({"type": "text", "data": {"text": text}})
            alt_parts.append(text)

        for url in self._iter_picture_urls(content):
            if url:
                segments.append({"type": "image", "data": {"file": url}})
                alt_parts.append("[图片]")
                raw_type = "picture"
        return raw_type, segments, alt_parts

    @staticmethod
    def _iter_picture_urls(content: dict):
        """兼容三种图片结构：url 字符串（svr_sync Picture）/ url 数组 / pictures 数组"""
        url = content.get("url")
        if isinstance(url, str) and url:
            yield url
        elif isinstance(url, list):
            for item in url:
                if isinstance(item, str):
                    yield item
        for pic in content.get("pictures", []) or []:
            if isinstance(pic, dict) and pic.get("url"):
                yield str(pic["url"])

    @staticmethod
    def _normalize_timestamp(timestamp) -> int:
        """秒级时间戳，缺省/异常时取当前时间；毫秒自动降为秒"""
        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            return int(time.time())
        if ts > 10**12:
            ts //= 1000
        return ts
