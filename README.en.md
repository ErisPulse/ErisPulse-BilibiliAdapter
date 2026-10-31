[English](README.en.md) | [简体中文](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-BilibiliAdapter" />

# ErisPulse-BilibiliAdapter

**ErisPulse Bilibili DM adapter — QR/Cookie login, event-driven DMs, multi-account**

<p>
  <a href="https://pypi.org/project/ErisPulse-BilibiliAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-BilibiliAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-BilibiliAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-BilibiliAdapter/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## Introduction

BilibiliAdapter is a Bilibili direct-message adapter built on [bilibili-api-python](https://github.com/Passkou/bilibili-api), providing event-driven DM send/receive.

**Highlights:**
- **Dual login**: Dashboard QR-code login (credentials written to config automatically) / manual Cookie credentials
- **Event-driven DMs**: text / picture messages received in real time as standard OneBot12 events
- **Picture in/out**: inbound as image segment (URL); outbound supports URL / local path
- **Multi-account**: one Bilibili account per entry under `accounts`, independent session listeners
- **Safe QR flow**: QR session tokens prevent unauthorized polling; credentials shown as passwords in the panel

## Installation

```bash
epsdk install BilibiliAdapter
```

или:

```bash
pip install ErisPulse-BilibiliAdapter
```

## Configuration

**Option 1: QR-code login (recommended)**

```toml
[BilibiliAdapter.accounts.default]
login_mode = "qrcode"
bot_id = ""                    # auto-detect
enabled = true
```

> After saving, open **Dashboard → Component Config → Bilibili → Add account wizard**, choose "Scan QR to log in", scan with the Bilibili APP and credentials are written to config automatically.

**Option 2: Cookie credentials**

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

> To get cookies: log in to Bilibili in your browser → F12 devtools → Application → Cookies → copy the fields.

**Configuration notes (per account):**
- `login_mode`: `cookie` (manual credentials) or `qrcode` (panel scan, recommended)
- `sessdata` / `bili_jct`: login cookies (required for cookie mode, shown as passwords)
- `buvid3`: device fingerprint cookie (optional, reduces risk-control probability)
- `dedeuserid`: account UID (optional, default source for bot_id)
- `bot_id`: account UID (auto-detected after login when empty)

## Messaging examples

```python
from ErisPulse import sdk
bili = sdk.adapter.get("bilibili")

# Send a text DM (target is the peer UID)
await bili.Send.To("user", "123456789").Text("Hello Bilibili!")

# Send a picture (URL or local path)
await bili.Send.To("user", "123456789").Image("https://example.com/pic.jpg")

# Reply (chained modifier)
await bili.Send.To("user", "123456789").Reply("msg_key").Text("Got it!")

# Multi-account
await bili.Send.Using("account2").To("user", "123456789").Text("From the second account")

# OneBot12 standard segments
message = [
    {"type": "text", "data": {"text": "line one"}},
    {"type": "image", "data": {"file": "https://example.com/img.jpg"}},
]
await bili.Send.To("user", "123456789").Raw_ob12(message)
```

## Standard Api actions

```python
# Self info
result = await bili.Api.get_self_info()           # {user_id, user_name, avatar}

# Public user info (nickname / avatar)
result = await bili.Api.get_user_info("123456789")

# Fetch history messages of a session
result = await bili.Api.get_session_msgs("123456789", begin_seqno=0)

# Status & version
result = await bili.Api.get_status()
result = await bili.Api.get_version()

# Multi-account
result = await bili.Api.Using("account2").get_self_info()
```

## Event listening examples

### Using the Event module (recommended)

```python
@sdk.adapter.on_message()
async def on_message(event):
    if event["platform"] == "bilibili":
        sender = event["user_id"]             # peer UID
        text = event["alt_message"]           # plain text content
        await event.reply("Got it!")          # quick reply
```

### Using platform raw events

```python
@sdk.adapter.on("message")
async def handle_message(event):
    if event["platform"] == "bilibili":
        raw = event["bilibili_raw"]           # raw Bilibili DM payload
        print(f"DM from: {raw.get('sender_uid')}")
```

## Platform event mapping

| Bilibili DM event | Adapter event |
|-------------------|---------------|
| TEXT (text message) | message (text segment) |
| PICTURE (picture message) | message (image segment) |
| WITHDRAW (recall) | logged only |

## Important notes:
1. **Bilibili has no official personal Bot API** — this adapter uses the web DM interface via simulated login (unofficial)
2. **Throttle your sends**: high-frequency / bulk DMs easily trigger risk control (DM功能 temporary ban); add rate limiting on the module side
3. Do not use for harassment or bulk marketing; follow Bilibili community rules
4. Cookies equal full account access — keep them safe; credential fields are masked in the panel
5. Only direct chats are supported; fan-group chats are not
6. Inbound pictures become image segments (URL); outbound pictures accept URL / local path
7. When the login state expires (cookies stale) the adapter logs errors — re-scan or update cookies

---

### Reference links
- [ErisPulse main repository](https://github.com/ErisPulse/ErisPulse/)
- [bilibili-api-python](https://github.com/Passkou/bilibili-api)
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)
- [Module development guide](https://www.erisdev.com/#docs/developer-guide/README.md)
