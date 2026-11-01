[English](README.en.md) | [简体中文](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-BilibiliAdapter" />

# ErisPulse-BilibiliAdapter

**ErisPulse Bilibili DM アダプタ — QR/Cookie ログイン、イベント駆動 DM、マルチアカウント**

<p>
  <a href="https://pypi.org/project/ErisPulse-BilibiliAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-BilibiliAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-BilibiliAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-BilibiliAdapter/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## 概要

BilibiliAdapter は [bilibili-api-python](https://github.com/Passkou/bilibili-api) ベースのビリビリ DM アダプタで、イベント駆動の DM 送受信を提供します。

**ハイライト：**
- **二つのログイン方式**：ダッシュボードの QR スキャン（認証情報を自動保存）/ Cookie 手動入力
- **イベント駆動 DM**：テキスト / 画像メッセージをリアルタイム受信し、標準 OneBot12 イベントへ変換
- **画像送受信**：受信は image セグメント（URL）；送信は URL / ローカルパス対応
- **マルチアカウント**：`accounts` の各エントリが一つの Bilibili アカウント
- **安全な QR**：セッショントークンで未認可ポーリングを防止；認証情報はパスワード表示

## インストール

```bash
epsdk install BilibiliAdapter
```

или:

```bash
pip install ErisPulse-BilibiliAdapter
```

## 設定

**方法 1：QR スキャンログイン（推奨）**

```toml
[BilibiliAdapter.accounts.default]
login_mode = "qrcode"
bot_id = ""                    # auto-detect
enabled = true
```

> 保存後、**ダッシュボード → コンポーネント設定 → Bilibili → アカウント追加ウィザード**で「QR スキャンでログイン」を選択し、Bilibili APP でスキャンすると認証情報が自動保存されます。

**方法 2：Cookie 認証情報**

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

> Cookie の取得：ブラウザで Bilibili にログイン → F12 開発者ツール → Application → Cookies → 該当フィールドをコピー。

**設定項目（アカウントごと）：**
- `login_mode`：`cookie`（手動入力）または `qrcode`（パネルスキャン、推奨）
- `sessdata` / `bili_jct`：ログイン Cookie（cookie モードでは必須、パスワード表示）
- `buvid3`：デバイス指紋 Cookie（任意、リスク対策）
- `dedeuserid`：アカウント UID（任意、bot_id のデフォルトソース）
- `bot_id`：アカウント UID（空欄でログイン後に自動取得）

## 送信例

```python
from ErisPulse import sdk
bili = sdk.adapter.get("bilibili")

# テキスト DM 送信（target は相手の UID）
await bili.Send.To("user", "123456789").Text("Hello Bilibili!")

# 画像送信（URL またはローカルパス）
await bili.Send.To("user", "123456789").Image("https://example.com/pic.jpg")

# 返信（チェーン修飾）
await bili.Send.To("user", "123456789").Reply("msg_key").Text("受信！")

# マルチアカウント
await bili.Send.Using("account2").To("user", "123456789").Text("2 つ目のアカウントから")

# OneBot12 標準セグメント
message = [
    {"type": "text", "data": {"text": "一行目"}},
    {"type": "image", "data": {"file": "https://example.com/img.jpg"}},
]
await bili.Send.To("user", "123456789").Raw_ob12(message)
```

## 標準 Api アクション

```python
# 自身の情報
result = await bili.Api.get_self_info()           # {user_id, user_name, avatar}

# ユーザー公開情報（ニックネーム/アバター）
result = await bili.Api.get_user_info("123456789")

# 指定セッションの履歴取得
result = await bili.Api.get_session_msgs("123456789", begin_seqno=0)

# 状態とバージョン
result = await bili.Api.get_status()
result = await bili.Api.get_version()

# マルチアカウント
result = await bili.Api.Using("account2").get_self_info()
```

## イベント監視例

### Event モジュール使用（推奨）

```python
@sdk.adapter.on_message()
async def on_message(event):
    if event["platform"] == "bilibili":
        sender = event["user_id"]             # 相手の UID
        text = event["alt_message"]           # 平文
        await event.reply("受信！")           # 簡易返信
```

### プラットフォーム生イベント

```python
@sdk.adapter.on("message")
async def handle_message(event):
    if event["platform"] == "bilibili":
        raw = event["bilibili_raw"]           # 生の DM ペイロード
        print(f"DM from: {raw.get('sender_uid')}")
```

## イベントマッピング

| Bilibili DM イベント | アダプタイベント |
|----------------------|------------------|
| TEXT（テキスト） | message（text セグメント） |
| PICTURE（画像） | message（image セグメント） |
| WITHDRAW（取り消し） | ログ記録のみ |

## 注意事項：
1. **Bilibili に公式の個人 Bot API はありません** — Web DM インターフェースを模擬ログインで利用する非公式方式です
2. **送信頻度を制御してください**：高頻度/一括 DM はリスク制御を誘発しやすい（DM 機能の一時停止）
3. 嫌がらせや一括マーケティングへの使用は禁止；コミュニティルールを遵守
4. Cookie はアカウントのログイン状態そのものです。取り扱いに注意；パネルではパスワード表示
5. DM は 1 対 1 のみ対応；ファングループチャットは未対応
6. 受信画像は image セグメント（URL）；送信画像は URL / ローカルパス対応
7. ログイン状態の失効（Cookie 期限切れ）時はエラーログ記録——再スキャンまたは Cookie 更新が必要

---

### 参考リンク
- [ErisPulse メインリポジトリ](https://github.com/ErisPulse/ErisPulse/)
- [bilibili-api-python](https://github.com/Passkou/bilibili-api)
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)
- [モジュール開発ガイド](https://www.erisdev.com/#docs/developer-guide/README.md)
