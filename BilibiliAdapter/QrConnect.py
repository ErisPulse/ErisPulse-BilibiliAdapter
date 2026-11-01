"""
B 站网页版扫码登录协议实现

协议流程（passport web 端点）：
1. GET https://passport.bilibili.com/x/passport-login/web/qrcode/generate
   → {"code":0,"data":{"qrcode_key":...,"url":...}}
2. 二维码内容为 data.url，用 B 站 APP 扫码并确认
3. GET https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key=...
   → data.code: 86101=未扫码 86090=已扫待确认 86038=已过期 0=成功
4. 成功时 data.url 为 crossDomain ticket 跳转地址，登录 Cookie
   （SESSDATA / bili_jct / DedeUserID）在手动跟随该跳转链的
   Set-Cookie 响应头中（不在 URL 参数里），最多跟随 6 跳。

风控注意：passport 接口对非浏览器 UA 返回 412，必须携带浏览器
User-Agent 与 Referer。
"""
import asyncio

from ErisPulse.Core import client

__all__ = ["QrLoginSession", "QrStatus", "PASSPORT_UA"]

PASSPORT_HOST = "passport.bilibili.com"
GENERATE_URL = f"https://{PASSPORT_HOST}/x/passport-login/web/qrcode/generate"
POLL_URL = f"https://{PASSPORT_HOST}/x/passport-login/web/qrcode/poll"

PASSPORT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_HEADERS = {
    "User-Agent": PASSPORT_UA,
    "Referer": f"https://{PASSPORT_HOST}/",
}


class QrStatus:
    PENDING = "pending"    # 未扫码
    SCAN = "scan"          # 已扫码待确认
    DONE = "done"          # 登录成功
    TIMEOUT = "timeout"    # 二维码已过期


class QrLoginError(RuntimeError):
    """passport 接口异常（风控拦截 / 非 JSON 响应 / 业务错误）"""


class QrLoginSession:
    """一次扫码登录会话：generate() 拿二维码 → 前端展示 → poll() 查询结果"""

    def __init__(self, qrcode_key: str, qr_url: str):
        self.qrcode_key = qrcode_key
        self.qr_url = qr_url

    @classmethod
    async def generate(cls) -> "QrLoginSession":
        """生成登录二维码，返回会话实例"""
        resp = await client.get(GENERATE_URL, headers=_HEADERS, timeout=15)
        if resp.status != 200:
            raise QrLoginError(f"二维码生成被拒 (HTTP {resp.status})")
        result = await _json_or_raise(resp, "二维码生成")
        if (result or {}).get("code") != 0:
            raise QrLoginError(f"生成二维码失败: {result}")
        data = result.get("data") or {}
        qrcode_key = str(data.get("qrcode_key") or "")
        qr_url = str(data.get("url") or "")
        if not qrcode_key or not qr_url:
            raise QrLoginError("生成二维码响应缺少 qrcode_key/url")
        return cls(qrcode_key, qr_url)

    async def poll(self) -> dict:
        """单次轮询：{"status": str, "credentials"?: {...}}"""
        resp = await client.get(
            POLL_URL, params={"qrcode_key": self.qrcode_key},
            headers=_HEADERS, timeout=15,
        )
        if resp.status != 200:
            raise QrLoginError(f"扫码轮询被拒 (HTTP {resp.status})")
        result = await _json_or_raise(resp, "扫码轮询")
        if (result or {}).get("code") != 0:
            raise QrLoginError(f"扫码轮询失败: {result}")

        data = result.get("data") or {}
        # 86101=未扫码 86090=已扫待确认 86038=已过期 0=成功
        # code=0 是合法值，不能用 `or` 兜底（0 or 86101 会吞掉成功状态）
        raw_code = data.get("code")
        code = int(raw_code) if raw_code is not None else 86101
        status = {
            0: QrStatus.DONE,
            86090: QrStatus.SCAN,
            86038: QrStatus.TIMEOUT,
        }.get(code, QrStatus.PENDING)
        out = {"status": status}
        if status == QrStatus.DONE:
            cross_url = str(data.get("url") or "")
            refresh_token = str(data.get("refresh_token") or "")
            # ticket 有效期极短，网络抖动导致提取失败时原链立即重试一次
            try:
                out["credentials"] = await _extract_credentials(cross_url, refresh_token)
            except QrLoginError:
                await asyncio.sleep(0.5)
                out["credentials"] = await _extract_credentials(cross_url, refresh_token)
        return out


async def _json_or_raise(resp, action: str) -> dict:
    try:
        return await resp.json()
    except Exception:
        text = ""
        try:
            text = (await resp.text())[:150]
        except Exception:
            pass
        raise QrLoginError(f"{action}响应非 JSON: {text}")


async def _extract_credentials(cross_url: str, refresh_token: str) -> dict:
    """跟随 crossDomain 跳转链，从 Set-Cookie 响应头提取登录凭据"""
    sessdata = bili_jct = dedeuserid = ""
    hop_url = cross_url
    for _hop in range(6):
        resp = await client.get(
            hop_url,
            headers={"User-Agent": PASSPORT_UA, "Referer": "https://www.bilibili.com/"},
            timeout=15,
            allow_redirects=False,
        )
        for cookie_header in resp.headers.getall("Set-Cookie", []):
            pair = cookie_header.split(";", 1)[0]
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            if key == "SESSDATA" and value:
                sessdata = value
            elif key == "bili_jct" and value:
                bili_jct = value
            elif key == "DedeUserID" and value:
                dedeuserid = value
        next_url = resp.headers.get("Location")
        if not next_url:
            break
        hop_url = next_url

    if not sessdata or not bili_jct:
        raise QrLoginError("扫码成功但凭据提取为空，请重试或改用 Cookie 模式")
    return {
        "sessdata": sessdata,
        "bili_jct": bili_jct,
        "dedeuserid": dedeuserid,
        "refresh_token": refresh_token,
    }
