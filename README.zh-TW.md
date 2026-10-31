[English](README.en.md) | [简体中文](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-BilibiliAdapter" />

# ErisPulse-BilibiliAdapter

**ErisPulse B 站私訊適配器 — 掃碼登入 / Cookie 憑證 / 事件驅動**

<p>
  <a href="https://pypi.org/project/ErisPulse-BilibiliAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-BilibiliAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-BilibiliAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-BilibiliAdapter/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## 簡介

BilibiliAdapter 是基於 [bilibili-api-python](https://github.com/Passkou/bilibili-api) 的 B 站私訊適配器，提供事件驅動的私訊收發能力。

**亮點：**
- **雙登入方式**：Dashboard 面板掃碼登入（憑證自動寫入配置）/ 手動填寫 Cookie 憑證
- **事件驅動私訊**：文字 / 圖片訊息即時接收，轉標準 OneBot12 事件
- **圖片收發**：接收轉 image 段（URL）；發送支援 URL / 本機路徑
- **多帳戶**：`accounts` 下每個帳戶一個 B 站帳號，獨立會話監聽
- **掃碼安全**：二維碼會話令牌防未授權輪詢；憑證面板密碼形態顯示

## 安裝

```bash
epsdk install BilibiliAdapter
```

или:

```bash
pip install ErisPulse-BilibiliAdapter
```

## 配置說明

**方式一：掃碼登入（推薦）**

```toml
[BilibiliAdapter.accounts.default]
login_mode = "qrcode"
bot_id = ""                    # auto-detect
enabled = true
```

> 配置完成後在 **Dashboard → 元件配置 → Bilibili → 新增帳戶嚮導** 中選擇「掃碼登入 B 站」，使用 B 站 APP 掃碼確認，憑證自動寫入配置。

**方式二：Cookie 憑證**

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

> Cookie 獲取：瀏覽器登入 B 站 → F12 開發者工具 → Application → Cookies → 複製對應欄位。

**配置項說明（每個帳戶）：**
- `login_mode`：登入方式，`cookie`（手填憑證）或 `qrcode`（面板掃碼，推薦）
- `sessdata` / `bili_jct`：登入態 Cookie（cookie 模式必填，面板密碼形態顯示）
- `buvid3`：設備指紋 Cookie（可選，降低風控機率）
- `dedeuserid`：帳號 UID（可選，也是 bot_id 的預設來源）
- `bot_id`：帳號 UID（留空登入後自動取得）

## 訊息傳送範例

```python
from ErisPulse import sdk
bili = sdk.adapter.get("bilibili")

# 傳送文字私訊（target 為對方 UID）
await bili.Send.To("user", "123456789").Text("Hello Bilibili!")

# 傳送圖片（URL 或本機路徑）
await bili.Send.To("user", "123456789").Image("https://example.com/pic.jpg")

# 回覆訊息（鏈式修飾）
await bili.Send.To("user", "123456789").Reply("msg_key").Text("收到！")

# 多帳戶
await bili.Send.Using("account2").To("user", "123456789").Text("來自第二個帳號")

# OneBot12 標準段傳送
message = [
    {"type": "text", "data": {"text": "第一行"}},
    {"type": "image", "data": {"file": "https://example.com/img.jpg"}},
]
await bili.Send.To("user", "123456789").Raw_ob12(message)
```

## 標準 Api 動作

```python
# 自身資訊
result = await bili.Api.get_self_info()           # {user_id, user_name, avatar}

# 使用者公開資訊（暱稱/頭像）
result = await bili.Api.get_user_info("123456789")

# 拉取指定會話歷史訊息
result = await bili.Api.get_session_msgs("123456789", begin_seqno=0)

# 執行狀態與版本
result = await bili.Api.get_status()
result = await bili.Api.get_version()

# 多帳戶
result = await bili.Api.Using("account2").get_self_info()
```

## 事件監聽範例

### 使用 Event 模組（推薦）

```python
@sdk.adapter.on_message()
async def on_message(event):
    if event["platform"] == "bilibili":
        sender = event["user_id"]             # 對方 UID
        text = event["alt_message"]           # 純文字內容
        await event.reply("收到！")           # 快捷回覆
```

### 使用平台原生事件

```python
@sdk.adapter.on("message")
async def handle_message(event):
    if event["platform"] == "bilibili":
        raw = event["bilibili_raw"]           # B 站原始私訊資料
        print(f"私訊來自: {raw.get('sender_uid')}")
```

## 平台事件映射關係

| B 站私訊事件 | Adapter 事件 |
|--------------|--------------|
| TEXT（文字訊息） | message（text 段） |
| PICTURE（圖片訊息） | message（image 段） |
| WITHDRAW（撤回） | 僅記錄日誌 |

## 注意事項：
1. **B 站無官方個人 Bot API**，本適配器透過模擬登入使用 Web 私訊介面，屬非官方用法
2. **請控制傳送頻率**：高頻/批次私訊極易觸發風控（帳號私訊功能被臨時禁言），建議模組側加節流
3. 請勿用於騷擾、行銷群發等違規用途，遵守 B 站社群規則
4. Cookie 憑證等同帳號登入態，注意保管；面板中憑證欄位以密碼形態顯示
5. 私訊僅支援單聊；粉絲群聊暫不支援
6. 圖片接收轉 image 段（URL），傳送圖片支援 URL / 本機路徑
7. 登入態失效（Cookie 過期）時適配器會記錄錯誤日誌，請重新掃碼或更新 Cookie

---

### 參考連結
- [ErisPulse 主庫](https://github.com/ErisPulse/ErisPulse/)
- [bilibili-api-python](https://github.com/Passkou/bilibili-api)
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)
- [模組開發指南](https://www.erisdev.com/#docs/developer-guide/README.md)
