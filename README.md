[English](README.en.md) | [简体中文](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-BilibiliAdapter" />

# ErisPulse-BilibiliAdapter

**ErisPulse B 站私信适配器 — 扫码登录 / Cookie 凭据 / 事件驱动**

<p>
  <a href="https://pypi.org/project/ErisPulse-BilibiliAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-BilibiliAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-BilibiliAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-BilibiliAdapter/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## 简介

BilibiliAdapter 是基于 [bilibili-api-python](https://github.com/Passkou/bilibili-api) 的 B 站私信适配器，提供事件驱动的私信收发能力。

**亮点：**
- 双登录方式：Dashboard 面板扫码登录（凭据自动写入配置）/ 手动填写 Cookie 凭据
- 事件驱动私信：文本 / 图片消息实时接收，转标准 OneBot12 事件
- 图片收发：接收转 image 段（URL）；发送支持 URL / 本地路径
- 多账户：`accounts` 下每个账户一个 B 站账号，独立会话监听
- 扫码安全：二维码会话令牌防未授权轮询；凭据面板密码形态展示

## 安装

```bash
epsdk install BilibiliAdapter
```

или:

```bash
pip install ErisPulse-BilibiliAdapter
```

## 配置说明

**方式一：扫码登录（推荐）**

```toml
[BilibiliAdapter.accounts.default]
login_mode = "qrcode"
bot_id = ""                    # auto-detect
enabled = true
```

> 配置完成后在 **Dashboard → 组件配置 → Bilibili → 添加账户向导** 中选择「扫码登录 B 站」，使用 B 站 APP 扫码确认，凭据自动写入配置。

**方式二：Cookie 凭据**

```toml
[BilibiliAdapter.accounts.default]
login_mode = "cookie"
sessdata = "YOUR_SESSDATA"     # required
bili_jct = "YOUR_BILI_JCT"     # required
buvid3 = "YOUR_BUVID3"         # optional
dedeuserid = "YOUR_UID"        # optional
bot_id = ""                    # auto-detect
enabled = true
```

> Cookie 获取：浏览器登录 B 站 → F12 开发者工具 → Application → Cookies → 复制对应字段。

**配置项说明（每个账户）：**
- `login_mode`：登录方式，`cookie`（手填凭据）或 `qrcode`（面板扫码，推荐）
- `sessdata` / `bili_jct`：登录态 Cookie（cookie 模式必填，面板密码形态显示）
- `buvid3`：设备指纹 Cookie（可选，降低风控概率）
- `dedeuserid`：账号 UID（可选，也是 bot_id 的默认来源）
- `bot_id`：账号 UID（留空登录后自动获取）

## 消息发送示例

```python
from ErisPulse import sdk
bili = sdk.adapter.get("bilibili")

# 发送文本私信（target 为对方 UID）
await bili.Send.To("user", "123456789").Text("Hello Bilibili!")

# 发送图片（URL 或本地路径）
await bili.Send.To("user", "123456789").Image("https://example.com/pic.jpg")

# 回复消息（链式修饰）
await bili.Send.To("user", "123456789").Reply("msg_key").Text("收到！")

# 多账户
await bili.Send.Using("account2").To("user", "123456789").Text("来自第二个账号")

# OneBot12 标准段发送
message = [
    {"type": "text", "data": {"text": "第一行"}},
    {"type": "image", "data": {"file": "https://example.com/img.jpg"}},
]
await bili.Send.To("user", "123456789").Raw_ob12(message)
```

## 标准 Api 动作

```python
# 自身信息
result = await bili.Api.get_self_info()           # {user_id, user_name, avatar}

# 用户公开信息（昵称/头像）
result = await bili.Api.get_user_info("123456789")

# 拉取指定会话历史消息
result = await bili.Api.get_session_msgs("123456789", begin_seqno=0)

# 运行状态与版本
result = await bili.Api.get_status()
result = await bili.Api.get_version()

# 多账户
result = await bili.Api.Using("account2").get_self_info()
```

## 事件监听示例

### 使用 Event 模块（推荐）

```python
@sdk.adapter.on_message()
async def on_message(event):
    if event["platform"] == "bilibili":
        sender = event["user_id"]             # 对方 UID
        text = event["alt_message"]           # 纯文本内容
        await event.reply("收到！")           # 快捷回复
```

### 使用平台原生事件

```python
@sdk.adapter.on("message")
async def handle_message(event):
    if event["platform"] == "bilibili":
        raw = event["bilibili_raw"]           # B 站原始私信数据
        print(f"私信来自: {raw.get('sender_uid')}")
```

## 平台事件映射关系

| B 站私信事件 | Adapter 事件 |
|--------------|--------------|
| TEXT（文本消息） | message（text 段） |
| PICTURE（图片消息） | message（image 段） |
| WITHDRAW（撤回） | 仅记录日志 |

## 注意事项：
1. **B 站无官方个人 Bot API**，本适配器通过模拟登录使用 Web 私信接口，属非官方用法
2. **请控制发送频率**：高频/批量私信极易触发风控（账号私信功能被临时禁言），建议模块侧加节流
3. 请勿用于骚扰、营销群发等违规用途，遵守 B 站社区规则
4. Cookie 凭据等同账号登录态，注意保管；面板中凭据字段以密码形态显示
5. 私信仅支持单聊；粉丝群聊暂不支持
6. 图片接收转 image 段（URL），发送图片支持 URL / 本地路径
7. 登录态失效（Cookie 过期）时适配器会记录错误日志，请重新扫码或更新 Cookie

---

### 参考链接
- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse/)
- [bilibili-api-python](https://github.com/Passkou/bilibili-api)
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)
- [模块开发指南](https://www.erisdev.com/#docs/developer-guide/README.md)
