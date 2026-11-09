import asyncio
import json
import re
import time as _time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

from ErisPulse import sdk
from ErisPulse.Core import client
from ErisPulse.Core.Bases import BaseConfig, BotAccountConfig, BaseAdapter
try:
    from ErisPulse.runtime.tasks import spawn_background
except ImportError:  # pragma: no cover
    spawn_background = None

__version__ = "0.3.1"

MIN_FRAMEWORK_VERSION = (2, 7, 1)


def _parse_version(version_str: str):
    try:
        parts = []
        for part in version_str.split("."):
            digits = ""
            for ch in part:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            parts.append(int(digits or 0))
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])
    except Exception:
        return (0, 0, 0)


def _check_framework_version() -> bool:
    try:
        raw = sdk.__version__ if hasattr(sdk, "__version__") else sdk.version
        if callable(raw):
            raw = raw()
        current = _parse_version(str(raw))
        if current < MIN_FRAMEWORK_VERSION:
            print(
                f"警告: ErisPulse 版本过低 (当前 {current}，需要 >= "
                f"{MIN_FRAMEWORK_VERSION})，BilibiliAdapter 可能无法正常工作"
            )
            return False
        return True
    except Exception:
        return True


from bilibili_api import session as bili_session
from bilibili_api.utils.network import Credential

_EM_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(value) -> str:
    """搜索结果标题带 <em class="keyword"> 高亮标签，去标签留原文。"""
    return _EM_TAG_RE.sub("", str(value or "")).strip()


def _simplify_dynamics(data: dict) -> list:
    """动态列表归一化：图文/视频/转发都提炼成 {type,title/url/desc,author}。"""
    out = []
    for item in (data or {}).get("items") or []:
        modules = item.get("modules") or {}
        author = str(((modules.get("module_author") or {}).get("name")) or "")
        dynamic = modules.get("module_dynamic") or {}
        desc = str(((dynamic.get("desc") or {}).get("text")) or "").strip()
        major = dynamic.get("major") or {}
        archive = major.get("archive") or {}
        if archive:
            bvid = str(archive.get("bvid") or "")
            out.append({
                "type": "video",
                "title": _clean_text(archive.get("title")),
                "bvid": bvid,
                "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
                "desc": _clean_text(archive.get("desc") or desc)[:300],
                "author": author,
            })
        elif desc:
            out.append({"type": "text", "text": desc[:300], "author": author})
    return out


def _simplify_search(data: dict) -> list:
    out = []
    for item in (data or {}).get("result") or []:
        bvid = str(item.get("bvid") or "")
        out.append({
            "title": _clean_text(item.get("title")),
            "url": str(item.get("arcurl") or (f"https://www.bilibili.com/video/{bvid}" if bvid else "")),
            "bvid": bvid,
            "author": str(item.get("author") or ""),
            "play": item.get("play"),
            "danmaku": item.get("danmaku"),
            "description": _clean_text(item.get("description"))[:200],
        })
    return out


def _simplify_popular(data: dict) -> list:
    items = (data or {}).get("list") or []
    out = []
    for item in items:
        bvid = str(item.get("bvid") or "")
        owner = item.get("owner") or {}
        stat = item.get("stat") or {}
        out.append({
            "title": _clean_text(item.get("title")),
            "bvid": bvid,
            "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            "author": str(owner.get("name") or ""),
            "view": stat.get("view"),
            "danmaku": stat.get("danmaku"),
            "desc": _clean_text(item.get("desc"))[:200],
        })
    return out


def _bili_error_code(e: Exception) -> int:
    """bilibili_api 异常归类：网络类 33001，平台类 34100"""
    try:
        from bilibili_api.exceptions import NetworkException
        return 33001 if isinstance(e, NetworkException) else 34100
    except Exception:
        return 34100


def _forward_node_text(node: Dict) -> str:
    """提取合并转发节点 content 中全部 text 段文本（段间直接连接）"""
    data = node.get("data") or {}
    return "".join(
        str(seg.get("data", {}).get("text") or "")
        for seg in (data.get("content") or [])
        if isinstance(seg, dict) and seg.get("type") == "text"
    )


def _forward_nodes_plain(nodes, separator: str = "\n") -> str:
    """合并转发节点降级纯文本：每条「昵称: 正文」"""
    lines = []
    for node in nodes if isinstance(nodes, list) else [nodes]:
        if not isinstance(node, dict):
            continue
        data = node.get("data") or {}
        nickname = str(data.get("nickname") or "").strip()
        text = _forward_node_text(node).strip()
        if nickname and text:
            lines.append(f"{nickname}: {text}")
        elif text:
            lines.append(text)
    return separator.join(lines)


def _strip_file_scheme(path: str) -> str:
    """剥除 file:// 前缀并解码百分号编码（file:///D:/a%20b.png → D:/a b.png）"""
    if path.startswith("file://"):
        path = unquote(path[len("file://"):])
        if re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
    return path


@dataclass
class BilibiliAccountConfig(BotAccountConfig):
    """Bilibili 账户配置"""

    login_mode: str = field(
        default="cookie",
        metadata={
            "description": "登录方式：cookie=手动填写凭据，qrcode=面板扫码登录",
            "required": False,
            "ui": {
                "widget": "select",
                "group": "connection",
                "order": 1,
                "options": [
                    {"label": "Cookie 凭据", "value": "cookie"},
                    {"label": "扫码登录", "value": "qrcode"},
                ],
            },
        },
    )
    sessdata: str = field(
        default="",
        metadata={
            "description": "SESSDATA（浏览器 Cookie，登录后可见）",
            "required": False,
            "secret": True,
            "ui": {
                "widget": "password",
                "group": "connection",
                "order": 2,
                "show_if": {"field": "login_mode", "op": "eq", "value": "cookie"},
            },
        },
    )
    bili_jct: str = field(
        default="",
        metadata={
            "description": "bili_jct（浏览器 Cookie，csrf 令牌）",
            "required": False,
            "secret": True,
            "ui": {
                "widget": "password",
                "group": "connection",
                "order": 3,
                "show_if": {"field": "login_mode", "op": "eq", "value": "cookie"},
            },
        },
    )
    buvid3: str = field(
        default="",
        metadata={
            "description": "buvid3（浏览器 Cookie，降低风控概率）",
            "required": False,
            "secret": True,
            "ui": {
                "widget": "password",
                "group": "connection",
                "order": 4,
                "show_if": {"field": "login_mode", "op": "eq", "value": "cookie"},
            },
        },
    )
    dedeuserid: str = field(
        default="",
        metadata={
            "description": "DedeUserID（浏览器 Cookie，即账号 UID）",
            "required": False,
            "secret": True,
            "ui": {
                "widget": "password",
                "group": "connection",
                "order": 5,
                "show_if": {"field": "login_mode", "op": "eq", "value": "cookie"},
            },
        },
    )
    bot_id: str = field(
        default="",
        metadata={
            "description": "账号 UID（留空则登录后自动获取）",
            "required": False,
            "ui": {"widget": "text", "group": "basic", "order": 6},
        },
    )


BilibiliAccountConfig._schema_meta = {
    "group_labels": {
        "basic": {"i18n": "bilibili.group.basic", "default": "基本设置"},
        "connection": {"i18n": "bilibili.group.connection", "default": "登录凭据"},
    }
}


class BilibiliAdapter(BaseAdapter):
    """
    Bilibili 私信适配器

    基于 bilibili-api-python，Cookie / 扫码双登录，事件驱动的私信收发。

    {!--< tips >!--}
    1. 多账户：accounts 下每个账户对应一个 B 站账号
    2. 事件：私信消息（detail_type=private），PlatformEvent 提供 bilibili_raw 原始数据
    3. 发送：支持 text 段与 image 段（image 的 file 为 URL 或本地路径）
    4. 风控提醒：非官方接口，请控制发送频率，避免账号风控
    {!--< /tips >!--}
    """

    _platform = "bilibili"
    ConfigClass = None
    AccountConfigClass = BilibiliAccountConfig

    def __init__(self, sdk_ref=None):
        super().__init__(sdk_ref)
        _check_framework_version()
        self._runtimes: Dict[str, _AccountRuntime] = {}
        self._sessions: Dict[str, Any] = {}
        self._credentials: Dict[str, Credential] = {}
        self._account_tasks: Dict[str, asyncio.Task] = {}

    def _get_config_key(self) -> str:
        return "BilibiliAdapter"

    def _build_credential(self, account) -> Optional[Credential]:
        if account.login_mode == "cookie":
            if not (account.sessdata and account.bili_jct):
                return None
            return Credential(
                sessdata=account.sessdata,
                bili_jct=account.bili_jct,
                buvid3=account.buvid3 or None,
                dedeuserid=account.dedeuserid or None,
            )
        # qrcode 模式：凭据由扫码流程写入配置（sessdata 等字段），同样按 cookie 构建
        if account.sessdata and account.bili_jct:
            return Credential(
                sessdata=account.sessdata,
                bili_jct=account.bili_jct,
                buvid3=account.buvid3 or None,
                dedeuserid=account.dedeuserid or None,
            )
        return None

    async def _detect_bot_id(self, credential: Credential) -> str:
        info = await bili_session.get_self_info(credential)
        return str((info or {}).get("mid", ""))

    # ==================== 生命周期 ====================

    async def start(self):
        # 扫码端点随 start 无条件注册（reload 后路由会被框架清理，必须重注册）
        try:
            self._ensure_qr_routes()
        except Exception as e:
            self.logger.error(f"扫码路由注册异常: {e}")
        try:
            self._setup_dashboard_section()
        except Exception as e:
            self.logger.debug(f"面板扩展区注册跳过（Dashboard 未加载，加载后会自动补注册）: {e}")

        for name, account in self.enabled_accounts.items():
            credential = self._build_credential(account)
            if credential is None:
                self.logger.warning(
                    f"账户 {name} 缺少登录凭据——请在面板「添加账户向导」中扫码登录，"
                    "或填写 Cookie 凭据后保存"
                )
                continue

            bot_id = account.bot_id or await self._detect_bot_id(credential)
            self._credentials[name] = credential

            rt = self._runtimes.get(name)
            if rt is None:
                rt = _AccountRuntime(name, account, bot_id, credential)
                self._runtimes[name] = rt
            rt.config = account
            rt.bot_id = bot_id
            rt.credential = credential

            task = asyncio.create_task(self._run_account(rt))
            self._account_tasks[name] = task

            await self.emit_meta("connect", bot_id, user_name=rt.user_name)

        self.logger.info(
            f"Bilibili 适配器已启动，共 {len(self._account_tasks)} 个账户"
        )
        # 扫码端点必须随 start 注册（面板扫码依赖 /bilibili/qr/*）
        self._ensure_qr_routes()
        self._setup_dashboard_section()

    async def _run_account(self, rt: "_AccountRuntime"):
        """事件驱动接收：Session(credential) + on(TEXT/PICTURE/WITHDRAW) + run()"""
        session = bili_session.Session(rt.credential)
        self._sessions[rt.name] = session

        @session.on(bili_session.EventType.TEXT)
        async def _on_text(event):
            await self._emit_private_message(rt, event)

        @session.on(bili_session.EventType.PICTURE)
        async def _on_picture(event):
            await self._emit_private_message(rt, event)

        @session.on(bili_session.EventType.WITHDRAW)
        async def _on_withdraw(event):
            data = getattr(event, "data", {}) or {}
            self.logger.debug(f"账户 {rt.name} 对方撤回了消息: {data}")

        try:
            await session.run(exclude_self=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.error(f"账户 {rt.name} 私信会话异常退出: {e}")

    async def _emit_private_message(self, rt: "_AccountRuntime", event):
        try:
            data = getattr(event, "data", {}) or {}
            sender_uid = str(data.get("sender_uid") or data.get("sender_id") or "")
            if not sender_uid:
                return
            content = data.get("content") or {}
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except Exception:
                    content = {"text": content}

            raw_type = "text"
            message_segments = []
            alt_parts = []
            if isinstance(content, dict):
                txt = str(content.get("message") or content.get("content") or "")
                if txt:
                    message_segments.append({"type": "text", "data": {"text": txt}})
                    alt_parts.append(txt)
                for pic in content.get("pictures", []) or []:
                    url = pic.get("url") or pic.get("image_url") or ""
                    if url:
                        message_segments.append({"type": "image", "data": {"file": url}})
                        alt_parts.append("[图片]")
                        raw_type = "picture"
            if not message_segments:
                return

            self_info = {
                "platform": "bilibili",
                "user_id": rt.bot_id,
                "user_name": rt.user_name,
                "account_id": rt.name,
            }
            ev = {
                "id": str(uuid.uuid4()),
                "message_id": str(data.get("msg_key") or ""),
                "time": int(_time.time()),
                "type": "message",
                "detail_type": "private",
                "platform": "bilibili",
                "self": self_info,
                "user_id": sender_uid,
                "user_nickname": str(content.get("sender_name") or "") or None,
                "message": message_segments,
                "alt_message": " ".join(alt_parts),
                "bilibili_raw": data,
                "bilibili_raw_type": raw_type,
            }
            if ev["user_nickname"] is None:
                ev.pop("user_nickname")
            await self.emit_event(ev)
        except Exception as e:
            self.logger.error(f"处理 B 站私信事件失败: {e}")

    async def call_api(self, endpoint: str, _account_id: Optional[str] = None, **params):
        """API 动作统一入口（send_message / get_self_info 等）"""
        # 标准字段 account_id 与旧名 _account_id 双兼容（ApiDSL.Using 传标准名）
        account_id = params.pop("account_id", None) or _account_id
        rt = self._runtimes.get(account_id) if account_id else next(iter(self._runtimes.values()), None)
        if rt is None:
            return self.make_error(retcode=10003, message="账户不存在或未启动")
        if endpoint == "send_message":
            target_id = str(params.get("target_id") or "")
            if not target_id:
                return self.make_error(retcode=10003, message="缺少 target_id")
            message = params.get("message") or []
            texts = [str(seg.get("data", {}).get("text", "")) for seg in message if seg.get("type") == "text"]
            pictures = [seg.get("data", {}).get("file") for seg in message if seg.get("type") == "image"]
            result = None
            if texts:
                result = await self._send_text(rt, target_id, "".join(texts))
            for pic in pictures:
                if pic:
                    result = await self._send_picture(rt, target_id, pic)
            return result or self.make_error(retcode=10002, message="空消息")
        if endpoint == "get_self_info":
            info = await bili_session.get_self_info(rt.credential)
            return self.make_response(data=info, raw=info)
# ===== 内容浏览（供 QvQChat call_adapter_api / 生态模块使用）=====
        if endpoint == "get_user_dynamics":
            uid = str(params.get("uid") or "").strip()
            if not uid.isdigit():
                return self.make_error(retcode=10003, message="缺少有效的 uid")
            try:
                from bilibili_api import user as bili_user

                data = await bili_user.User(int(uid)).get_dynamics(
                    offset=int(params.get("offset") or 0)
                )
                items = _simplify_dynamics(data)
                return self.make_response(data={"uid": uid, "items": items, "count": len(items)})
            except Exception as e:
                return self.make_error(retcode=_bili_error_code(e), message=f"获取动态失败: {e}")
        if endpoint == "search_video":
            keyword = str(params.get("keyword") or "").strip()
            if not keyword:
                return self.make_error(retcode=10003, message="缺少 keyword")
            try:
                from bilibili_api import search as bili_search

                data = await bili_search.search_by_type(
                    keyword,
                    search_type=bili_search.SearchObjectType.VIDEO,
                    page=max(1, int(params.get("page") or 1)),
                )
                items = _simplify_search(data)
                return self.make_response(data={"keyword": keyword, "items": items, "count": len(items)})
            except Exception as e:
                return self.make_error(retcode=_bili_error_code(e), message=f"搜索失败: {e}")
        if endpoint == "get_popular":
            try:
                from bilibili_api import homepage as bili_homepage

                data = await bili_homepage.get_popularize()
                items = _simplify_popular(data)
                return self.make_response(data={"items": items, "count": len(items)})
            except Exception as e:
                return self.make_error(retcode=_bili_error_code(e), message=f"获取热门失败: {e}")
        return self.make_error(retcode=10002, message=f"不支持的动作: {endpoint}")

    async def shutdown(self):
        for session in self._sessions.values():
            try:
                await session.close()
            except Exception:
                pass
        self._sessions.clear()
        for task in self._account_tasks.values():
            task.cancel()
        if self._account_tasks:
            await asyncio.gather(*self._account_tasks.values(), return_exceptions=True)
        self._account_tasks.clear()
        for rt in self._runtimes.values():
            if rt.bot_id:
                try:
                    await self.emit_meta("disconnect", rt.bot_id)
                except Exception:
                    pass
        try:
            sdk.Dashboard.unregister_section("bilibili-qr")
        except Exception:
            pass
        self.logger.info("Bilibili 适配器已关闭")

    # ==================== 发送 ====================

    async def _send_text(self, rt: "_AccountRuntime", receiver_id: str, text: str) -> dict:
        result = await bili_session.send_msg(
            rt.credential, int(receiver_id), bili_session.EventType.TEXT, text
        )
        code = (result or {}).get("code", -1)
        if code != 0:
            return self.make_error(
                retcode=33100,
                message=f"B 站接口返回 code={code}: {(result or {}).get('message', '')}",
                raw=result,
            )
        msg_key = ((result or {}).get("data") or {}).get("msg_key", "")
        return self.make_response(data=result, message_id=str(msg_key), raw=result)

    @staticmethod
    def _detect_image_format(data: bytes) -> str:
        """按文件头魔数判断图片格式（png/jpg/gif/webp），未识别时返回 png"""
        if len(data) < 12:
            return "png"
        h = data[:16]
        if h[:8] == b"\x89PNG\r\n\x1a\n":
            return "png"
        if h[:2] == b"\xff\xd8":
            return "jpg"
        if h[:6] in (b"GIF87a", b"GIF89a"):
            return "gif"
        if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
            return "webp"
        return "png"

    async def _download_image(self, url: str) -> tuple:
        """下载 URL 图片为 (bytes, 失败原因)，成功时失败原因为 None"""
        try:
            resp = await client.get(url, timeout=30)
            status = getattr(resp, "status", 0)
            if status >= 400:
                return None, f"HTTP {status}"
            return await resp.read(), None
        except Exception as e:
            return None, str(e)

    async def _send_picture(self, rt: "_AccountRuntime", receiver_id: str, file_ref) -> dict:
        from bilibili_api.utils.picture import Picture

        if isinstance(file_ref, bytes):
            pic = Picture.from_content(file_ref, self._detect_image_format(file_ref))
        else:
            source = _strip_file_scheme(str(file_ref))
            if source.startswith(("http://", "https://")):
                # B 站私信图片要求自有图床内容：下载后经 from_content（url 为 bytes://）触发上传
                content, reason = await self._download_image(source)
                if content is None:
                    return self.make_error(
                        retcode=10002,
                        message=f"图片下载失败: {source} ({reason})",
                    )
                pic = Picture.from_content(content, self._detect_image_format(content))
            else:
                pic = Picture.from_file(source)
        result = await bili_session.send_msg(
            rt.credential, int(receiver_id), bili_session.EventType.PICTURE, pic
        )
        code = (result or {}).get("code", -1)
        if code != 0:
            return self.make_error(retcode=33100, message=f"B 站接口返回 code={code}", raw=result)
        msg_key = ((result or {}).get("data") or {}).get("msg_key", "")
        return self.make_response(data=result, message_id=str(msg_key), raw=result)

    # ==================== 发送 ====================

    class Send(BaseAdapter.Send):
        """Bilibili 消息发送（text / image；其余段报错说明）"""

        def Raw_ob12(self, message, **kwargs):
            ctx = self.send_context

            async def _send():
                adapter = self._adapter
                rt = adapter._runtimes.get(ctx.get("account_id") or next(iter(adapter._runtimes)))
                if rt is None:
                    return adapter.make_error(retcode=10003, message="账户不存在或未启动")
                target_id = ctx.get("target_id")
                if not target_id:
                    return adapter.make_error(retcode=10003, message="无法确定发送目标（需要 To('user', <uid>)）")

                segments = self._apply_modifiers(message)

                # 纯 node 列表：合并转发降级为「昵称: 正文」逐行纯文本
                if segments and all(
                    isinstance(seg, dict) and seg.get("type") == "node"
                    for seg in segments
                ):
                    node_text = _forward_nodes_plain(segments)
                    if not node_text:
                        return adapter.make_error(retcode=10002, message="node 段无有效文本内容")
                    return await adapter._send_text(rt, target_id, node_text)

                unsupported = []
                result = None
                sent = False
                pending_text = []

                async def _flush_text():
                    nonlocal result, sent
                    text = "".join(pending_text)
                    pending_text.clear()
                    if text:
                        result = await adapter._send_text(rt, target_id, text)
                        sent = True

                for seg in segments:
                    stype = seg.get("type")
                    data = seg.get("data", {}) or {}
                    if stype == "text":
                        pending_text.append(str(data.get("text", "")))
                    elif stype == "node":
                        node_text = _forward_nodes_plain(seg)
                        if node_text:
                            pending_text.append(node_text + "\n")
                    elif stype == "image":
                        await _flush_text()
                        pic = data.get("file")
                        if pic:
                            result = await adapter._send_picture(rt, target_id, pic)
                            sent = True
                    elif stype == "reply":
                        adapter.logger.warning(
                            f"B 站私信不支持 reply 段，已忽略（message_id={data.get('message_id', '')}）"
                        )
                    else:
                        unsupported.append(str(stype))

                await _flush_text()

                if not sent:
                    return adapter.make_error(
                        retcode=10002,
                        message="B 站私信仅支持 text/image 段"
                        + (f"，收到不支持段: {unsupported}" if unsupported else "，且消息为空"),
                    )
                if unsupported:
                    adapter.logger.warning(
                        f"B 站私信发送已跳过不支持的段: {', '.join(unsupported)}"
                    )
                    if result is not None:
                        note = f"已跳过不支持的段: {', '.join(unsupported)}"
                        result["message"] = (
                            f"{result['message']}；{note}" if result.get("message") else note
                        )
                return result

            return asyncio.create_task(_send())

    # ==================== Api ====================

    class Api(BaseAdapter.Api):
        """Bilibili 标准 API 动作"""

        async def get_self_info(self) -> dict:
            rt = self._adapter._current_runtime(self._account_id or self.api_context.get("account_id"))
            info = await bili_session.get_self_info(rt.credential)
            data = info or {}
            return self._adapter.make_response(
                data={
                    "user_id": str(data.get("mid", "")),
                    "user_name": data.get("name", ""),
                    "user_displayname": data.get("name", ""),
                    "user_remark": "",
                    "avatar": data.get("face", ""),
                },
                raw=info,
            )

        async def get_status(self) -> dict:
            return self._adapter.make_response(data={"status": "ok"})

        async def get_version(self) -> dict:
            from . import __version__

            return self._adapter.make_response(
                data={
                    "impl": "ErisPulse-BilibiliAdapter",
                    "version": __version__,
                    "onebot_version": "12",
                }
            )

        async def get_supported_actions(self) -> dict:
            return self._adapter.make_response(
                data=[
                    "get_self_info", "get_status", "get_version",
                    "get_supported_actions", "send_message",
                    "get_user_info", "get_session_msgs",
                ]
            )

        async def get_user_info(self, user_id: str) -> dict:
            """获取用户公开信息（昵称/头像）"""
            from bilibili_api import user as bili_user

            rt = self._adapter._current_runtime(self._account_id or self.api_context.get("account_id"))
            u = bili_user.User(int(user_id), credential=rt.credential)
            info = await u.get_info()
            data = info or {}
            return self._adapter.make_response(
                data={
                    "user_id": str(data.get("mid", user_id)),
                    "user_name": data.get("name", ""),
                    "user_displayname": data.get("name", ""),
                    "user_remark": "",
                    "avatar": data.get("face", ""),
                },
                raw=info,
            )

        async def get_session_msgs(self, talker_id: str, begin_seqno: int = 0) -> dict:
            """拉取指定会话的历史消息"""
            rt = self._adapter._current_runtime(self._account_id or self.api_context.get("account_id"))
            result = await bili_session.fetch_session_msgs(
                int(talker_id), rt.credential, begin_seqno=begin_seqno
            )
            return self._adapter.make_response(data=result, raw=result)

    def _current_runtime(self, account_id: Optional[str] = None):
        # 显式 Using() / 事件链路账户优先（ApiDSL.api_context 兜底），失效时回退首个账户
        name = account_id or getattr(self, "_api_account_id", None)
        if name and name in self._runtimes:
            return self._runtimes[name]
        return next(iter(self._runtimes.values()))

    # ==================== 扫码登录（面板扩展区） ====================

    def _setup_dashboard_section(self):
        def _register():
            try:
                dashboard = sdk.Dashboard
            except Exception:
                return False
            try:
                dashboard.register_section(
                    id="bilibili-qr",
                    target="account_wizard",
                    title="扫码登录 B 站",
                    title_en="Scan QR to log in",
                    icon_svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM21 14v.01M14 21v.01M17.5 17.5L21 21"/></svg>',
                    platforms=["bilibili"],
                    html=self._qr_section_html(),
                    order=10,
                )
                self.logger.info("已注册面板扫码登录扩展区")
                return True
            except Exception as e:
                self.logger.debug(f"面板扩展区注册失败: {e}")
                return False

        if _register():
            return

        async def _on_module_load(data):
            if (
                isinstance(data, dict)
                and data.get("module_name") == "Dashboard"
                and data.get("success")
            ):
                _register()
                sdk.lifecycle.unregister("module.load", _on_module_load)

        async def _on_init_complete(data):
            # 初始化完成后 Dashboard 若已加载（适配器先于模块启动的时序），补注册
            _register()
            try:
                sdk.lifecycle.unregister("core.init.complete", _on_init_complete)
            except Exception:
                pass

        try:
            sdk.lifecycle.register("module.load", _on_module_load)
            sdk.lifecycle.register("core.init.complete", _on_init_complete)
        except Exception:
            pass

    def _ensure_qr_routes(self):
        """扫码端点注册（幂等：先注销再注册，防配置热重载后路由被清而标志残留）"""
        from ErisPulse.Core import router

        try:
            router.unregister_http_route("bilibili", "/qr/start")
            router.unregister_http_route("bilibili", "/qr/poll")
        except Exception:
            pass
        self._qr_sessions: Dict[str, Any] = {}

        async def _qr_start(request):
            from fastapi.responses import JSONResponse
            import secrets as _secrets
            import qrcode as _qrcode

            resp = await client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', 'Referer': 'https://passport.bilibili.com/'},
                timeout=15,
            )
            if resp.status != 200:
                body = await resp.text()
                self.logger.error(f"二维码生成被拒: HTTP {resp.status} {body[:150]}")
                return JSONResponse({"success": False, "error": f"B 站风控拦截 (HTTP {resp.status})，请稍后重试"}, status_code=502)
            try:
                result = await resp.json()
            except Exception:
                body = await resp.text()
                self.logger.error(f"二维码生成响应非 JSON: {body[:150]}")
                return JSONResponse({"success": False, "error": "B 站返回异常响应"}, status_code=502)
            if (result or {}).get("code") != 0:
                return JSONResponse({"success": False, "error": f"生成二维码失败: {result}"}, status_code=502)
            data = result.get("data") or {}
            qrcode_key = str(data.get("qrcode_key") or "")
            qr_url = str(data.get("url") or "")
            if not qrcode_key or not qr_url:
                return JSONResponse({"success": False, "error": "缺少 qrcode_key"}, status_code=502)

            qr = _qrcode.QRCode(border=2, error_correction=_qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(qr_url)
            qr.make(fit=True)
            matrix = qr.get_matrix()
            n = len(matrix)
            parts = [f"M{x} {y}h1v1h-1z" for y, row in enumerate(matrix) for x, on in enumerate(row) if on]
            svg = (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" '
                f'shape-rendering="crispEdges" width="240" height="240">'
                f'<rect width="{n}" height="{n}" fill="#fff"/>'
                f'<path d="{"".join(parts)}" fill="#111"/></svg>'
            )
            poll_token = _secrets.token_urlsafe(24)
            self._qr_sessions[qrcode_key] = {"token": poll_token}
            return JSONResponse(
                {
                    "success": True,
                    "task_id": qrcode_key,
                    "poll_token": poll_token,
                    "qr_img": f"data:image/svg+xml;base64,"
                    + __import__("base64").b64encode(svg.encode()).decode(),
                }
            )

        async def _qr_poll(request):
            from fastapi.responses import JSONResponse

            body = {}
            try:
                body = await request.json()
            except Exception:
                pass
            qrcode_key = str(body.get("task_id") or "")
            token = str(body.get("poll_token") or "")
            entry = self._qr_sessions.get(qrcode_key)
            if not entry or entry["token"] != token:
                return JSONResponse({"success": False, "error": "unauthorized"}, status_code=403)

            resp = await client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                params={"qrcode_key": qrcode_key},
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', 'Referer': 'https://passport.bilibili.com/'},
                timeout=15,
            )
            if resp.status != 200:
                body = await resp.text()
                self.logger.error(f"扫码轮询被拒: HTTP {resp.status} {body[:150]}")
                return JSONResponse({"success": False, "error": f"B 站风控拦截 (HTTP {resp.status})"}, status_code=502)
            try:
                result = await resp.json()
            except Exception:
                body = await resp.text()
                self.logger.error(f"扫码轮询响应非 JSON: {body[:150]}")
                return JSONResponse({"success": False, "error": "B 站返回异常响应"}, status_code=502)
            if (result or {}).get("code") not in (0, 86038, 86090, 86101):
                return JSONResponse({"success": False, "error": f"轮询异常: {result}"}, status_code=502)
            data = result.get("data") or {}
            code = int(data.get("code") or result.get("code") or 0)

            # 86101=未扫码 86090=已扫待确认 86038=已过期 0=成功
            status = {0: "done", 86090: "scan", 86101: "pending", 86038: "timeout"}.get(code, "pending")
            out = {"success": True, "status": status}
            if code == 0:
                # B 站新协议：data.url 为 crossDomain ticket 跳转，cookie 在跳转响应的 Set-Cookie 里
                cross_url = str(data.get("url") or "")
                sessdata = bili_jct = dedeuserid = ""
                UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                hop_url = cross_url
                for _hop in range(6):
                    hop_resp = await client.get(
                        hop_url,
                        headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
                        timeout=15,
                        allow_redirects=False,
                    )
                    for cookie_header in hop_resp.headers.getall("Set-Cookie", []):
                        pair = cookie_header.split(";", 1)[0]
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            if k == "SESSDATA" and v:
                                sessdata = v
                            elif k == "bili_jct" and v:
                                bili_jct = v
                            elif k == "DedeUserID" and v:
                                dedeuserid = v
                    next_url = hop_resp.headers.get("Location")
                    if not next_url:
                        break
                    hop_url = next_url
                if not sessdata or not bili_jct:
                    self.logger.error(f"扫码成功但凭据提取为空（crossDomain: {cross_url[:120]}）")
                    self._qr_sessions.pop(qrcode_key, None)
                    return JSONResponse(
                        {"success": False, "error": "扫码成功但凭据提取为空，请重试或使用 Cookie 模式"}, status_code=500
                    )
                from ErisPulse.Core import config as _cfg
                from bilibili_api.utils.network import Credential

                credential = Credential(
                    sessdata=sessdata, bili_jct=bili_jct, dedeuserid=dedeuserid or None,
                    ac_time_value=str(data.get("refresh_token") or "") or None,
                )
                key = "BilibiliAdapter.accounts"
                accounts = _cfg.getConfig(key) or {}
                if not isinstance(accounts, dict):
                    accounts = {}
                dft = accounts.get("default")
                if isinstance(dft, dict) and not dft.get("sessdata"):
                    name = "default"
                else:
                    base, i2, name = "qr", 1, "qr"
                    while name in accounts and accounts[name].get("sessdata"):
                        i2 += 1
                        name = f"{base}{i2}"
                accounts[name] = {
                    "login_mode": "qrcode",
                    "sessdata": sessdata,
                    "bili_jct": bili_jct,
                    "buvid3": "",
                    "dedeuserid": dedeuserid,
                    "bot_id": dedeuserid,
                    "enabled": True,
                }
                _cfg.setConfig(key, accounts)
                self._qr_sessions.pop(qrcode_key, None)
                out["account"] = name
                self.logger.info(f"扫码登录完成，凭据已写入账户 {name}")
            elif code == 86038:
                self._qr_sessions.pop(qrcode_key, None)
            return JSONResponse(out)

        self.logger.debug("扫码登录端点已注册 (/bilibili/qr/*)")

    @staticmethod
    def _qr_section_html() -> str:
        return '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{color-scheme:light dark}
body{margin:0;padding:18px;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:transparent;color:inherit;display:flex;flex-direction:column;align-items:center;gap:12px}
#qr{border-radius:12px;overflow:hidden;box-shadow:0 0 0 1px rgba(128,128,128,.25);background:#fff;padding:8px;min-width:200px;min-height:200px;display:flex;align-items:center;justify-content:center}
#qr img{width:200px;height:200px;image-rendering:pixelated}
.st{font-size:13px;opacity:.75;text-align:center}
.ok{color:#16a34a;font-weight:600}
button{padding:8px 18px;border-radius:10px;border:1px solid rgba(128,128,128,.4);background:transparent;cursor:pointer;font-size:13px}
</style></head><body>
<div id="qr">…</div>
<div class="st" id="st">正在获取二维码…</div>
<button id="re" style="display:none" onclick="location.reload()">重新获取</button>
<script>
(async function(){
  var st = document.getElementById("st"), re = document.getElementById("re");
  var startResp = null;
  // 获取二维码（适配器热重载窗口内 404 自动重试）
  for (var attempt = 0; attempt < 6; attempt++) {
    try {
      var rr = await fetch("/bilibili/qr/start", {method:"POST"});
      if (rr.status === 404) { throw {retry: true}; }
      startResp = await rr.json();
      break;
    } catch (e) {
      if (attempt === 5) {
        st.textContent = "获取二维码失败: " + (e.msg || e.message || "start failed");
        re.style.display = "";
        return;
      }
      st.textContent = "适配器重启中，" + (5 - attempt) + " 秒后重试…";
      await new Promise(function(res){ setTimeout(res, 2000); });
    }
  }
  var d = startResp;
  if (!d || !d.success) {
    st.textContent = "获取二维码失败";
    re.style.display = "";
    return;
  }
  if (d.qr_img) {
    document.getElementById("qr").innerHTML = '<img src="' + d.qr_img + '" alt="QR">';
  }
  st.textContent = "请使用 B 站 APP 扫码并确认登录";
  var taskId = d.task_id, token = d.poll_token, n = 0;
  var timer = setInterval(async function(){
    n++;
    if(n > 90){
      clearInterval(timer);
      st.textContent = "二维码已过期";
      re.style.display = "";
      return;
    }
    try{
      var pr = await fetch("/bilibili/qr/poll", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({task_id:taskId, poll_token:token})});
      var pd = await pr.json();
      if(pd.success && pd.status === "done"){
        clearInterval(timer);
        st.className = "st ok";
        st.textContent = "登录成功，凭据已写入账户 " + (pd.account || "");
        setTimeout(function(){ parent.postMessage({type:"ep_section_done", success:true}, "*"); }, 900);
      } else if(pd.success && pd.status === "timeout"){
        clearInterval(timer);
        st.textContent = "二维码已过期";
        re.style.display = "";
      } else if(pd.success && pd.status === "scan"){
        st.textContent = "已扫码，请在手机上确认";
      }
    }catch(e){}
  }, 2000);
})();
</script></body></html>'''


class _AccountRuntime:
    """单个账户运行时状态"""

    __slots__ = ("name", "config", "bot_id", "credential", "user_name")

    def __init__(self, name: str, config, bot_id: str, credential):
        self.name = name
        self.config = config
        self.bot_id = bot_id
        self.credential = credential
        self.user_name = ""
