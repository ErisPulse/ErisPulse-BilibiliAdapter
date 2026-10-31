# ErisPulse BilibiliAdapter

**Bilibili 私信适配器 —— Cookie/扫码双登录、事件驱动收发、多账户。**

## 特性

- **双登录方式**：面板扫码（B 站 APP 扫码后凭据自动写入配置）/ 手动填 Cookie（SESSDATA/bili_jct/buvid3）
- **事件驱动**：`Session` 会话监听私信（文本/图片），转标准 OneBot12 事件
- **多账户**：`accounts` 下每个账户一个 B 站账号，`event.reply()` 自动路由
- **扫码登录**：通过 Dashboard 扩展区一键扫码，凭据自动落库
- 标准发送 DSL：`.Text()` / `.Image()`（URL 或本地路径）

## 安装

```bash
epsdk install BilibiliAdapter
```

或：

```bash
pip install ErisPulse-BilibiliAdapter
```

## 配置

```toml
[BilibiliAdapter.accounts.default]
login_mode = "cookie"          # cookie=手填凭据 / qrcode=面板扫码（推荐）
sessdata = "YOUR_SESSDATA"     # cookie 模式必填（浏览器 Cookie）
bili_jct = "YOUR_BILI_JCT"     # cookie 模式必填
buvid3 = "YOUR_BUVID3"         # 可选，降低风控概率
dedeuserid = "YOUR_UID"        # 可选
bot_id = ""                    # 留空自动获取
enabled = true
```

> 推荐 `qrcode` 模式：配置里只设 `login_mode = "qrcode"`，然后在 Dashboard → 组件配置 → 添加账户向导中选择「扫码登录 B 站」，扫码后凭据自动写入。

## 使用

```python
from ErisPulse import sdk
bili = sdk.adapter.get("bilibili")

# 发送私信（target 为对方 UID）
await bili.Send.To("user", "123456789").Text("Hello Bilibili!")
await bili.Send.To("user", "123456789").Image("https://example.com/pic.jpg")

# 接收私信（模块侧）
@sdk.adapter.on_message()
async def on_msg(event):
    if event["platform"] == "bilibili":
        await event.reply("收到！")
```

## ⚠️ 风控与合规提醒

- B 站**没有官方个人 Bot API**，本适配器通过模拟登录使用 Web 私信接口，属于非官方用法
- 请**控制发送频率**（建议加节流），高频/批量私信极易触发风控（账号临时禁言私信功能）
- 请勿用于骚扰、营销群发等违规用途，遵守 B 站社区规则
- Cookie 凭据等同账号登录态，注意保管（配置中的凭据字段在面板以密码形态显示）

## 平台限制

- 私信仅支持单聊（粉丝群聊暂不支持）
- 图片发送支持 URL / 本地路径（自动转 B 站图床？否——直接随私信发送）
- 撤回、系统消息等事件当前仅记录日志

## License

MIT
