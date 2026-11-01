[English](README.en.md) | [简体中文](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-BilibiliAdapter" />

# ErisPulse-BilibiliAdapter

**ErisPulse адаптер личных сообщений Bilibili — QR/Cookie вход, событийные ЛС, мультиаккаунт**

<p>
  <a href="https://pypi.org/project/ErisPulse-BilibiliAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-BilibiliAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-BilibiliAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-BilibiliAdapter/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## Введение

BilibiliAdapter — адаптер личных сообщений Bilibili на основе [bilibili-api-python](https://github.com/Passkou/bilibili-api) с событийной отправкой и приёмом ЛС.

**Возможности:**
- **Два способа входа**: сканирование QR в панели (учётные данные записываются автоматически) / ручной ввод Cookie
- **Событийные ЛС**: текст / картинки принимаются в реальном времени как стандартные события OneBot12
- **Картинки в обе стороны**: вход — сегмент image (URL); отправка — URL / локальный путь
- **Мультиаккаунт**: каждая запись в `accounts` — отдельный аккаунт Bilibili
- **Безопасный QR**: токены сессии защищают от несанкционированного опроса; данные скрыты в панели

## Установка

```bash
epsdk install BilibiliAdapter
```

или:

```bash
pip install ErisPulse-BilibiliAdapter
```

## Настройка

**Вариант 1: вход по QR (рекомендуется)**

```toml
[BilibiliAdapter.accounts.default]
login_mode = "qrcode"
bot_id = ""                    # auto-detect
enabled = true
```

> После сохранения откройте **Dashboard → Конфигурация компонентов → Bilibili → мастер добавления аккаунта**, выберите «Вход по QR», отсканируйте приложением Bilibili — данные запишутся автоматически.

**Вариант 2: Cookie-учётные данные**

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

> Получение Cookie: войдите в Bilibili в браузере → F12 → Application → Cookies → скопируйте поля.

**Параметры (на аккаунт):**
- `login_mode`: `cookie` (ручной ввод) или `qrcode` (сканирование в панели, рекомендуется)
- `sessdata` / `bili_jct`: cookie входа (обязательны для cookie-режима, скрыты в панели)
- `buvid3`: cookie отпечатка устройства (опционально, снижает риск блокировки)
- `dedeuserid`: UID аккаунта (опционально, источник bot_id)
- `bot_id`: UID аккаунта (определяется автоматически после входа, если пусто)

## Примеры отправки

```python
from ErisPulse import sdk
bili = sdk.adapter.get("bilibili")

# ЛС с текстом (target — UID собеседника)
await bili.Send.To("user", "123456789").Text("Hello Bilibili!")

# Отправка картинки (URL или локальный путь)
await bili.Send.To("user", "123456789").Image("https://example.com/pic.jpg")

# Ответ (цепной модификатор)
await bili.Send.To("user", "123456789").Reply("msg_key").Text("Получено!")

# Мультиаккаунт
await bili.Send.Using("account2").To("user", "123456789").Text("Со второго аккаунта")

# Стандартные сегменты OneBot12
message = [
    {"type": "text", "data": {"text": "строка один"}},
    {"type": "image", "data": {"file": "https://example.com/img.jpg"}},
]
await bili.Send.To("user", "123456789").Raw_ob12(message)
```

## Стандартные действия Api

```python
# Информация о себе
result = await bili.Api.get_self_info()           # {user_id, user_name, avatar}

# Публичная информация о пользователе
result = await bili.Api.get_user_info("123456789")

# История сообщений сессии
result = await bili.Api.get_session_msgs("123456789", begin_seqno=0)

# Статус и версия
result = await bili.Api.get_status()
result = await bili.Api.get_version()

# Мультиаккаунт
result = await bili.Api.Using("account2").get_self_info()
```

## Примеры прослушивания событий

### Через модуль Event (рекомендуется)

```python
@sdk.adapter.on_message()
async def on_message(event):
    if event["platform"] == "bilibili":
        sender = event["user_id"]             # UID собеседника
        text = event["alt_message"]           # текст
        await event.reply("Получено!")        # быстрый ответ
```

### Через сырые события платформы

```python
@sdk.adapter.on("message")
async def handle_message(event):
    if event["platform"] == "bilibili":
        raw = event["bilibili_raw"]           # исходные данные ЛС
        print(f"ЛС от: {raw.get('sender_uid')}")
```

## Соответствие событий

| Событие ЛС Bilibili | Событие адаптера |
|---------------------|------------------|
| TEXT (текст) | message (сегмент text) |
| PICTURE (картинка) | message (сегмент image) |
| WITHDRAW (отзыв) | только лог |

## Важные замечания:
1. **У Bilibili нет официального Bot API** — адаптер использует веб-интерфейс ЛС через имитацию входа (неофициально)
2. **Ограничивайте частоту отправки**: частые/массовые ЛС легко вызывают риск-контроль (временная блокировка ЛС)
3. Не используйте для спама и массовых рассылок; соблюдайте правила сообщества
4. Cookie равносильны доступу к аккаунту — храните аккуратно; в панели поля скрыты
5. Поддерживаются только личные чаты; фан-группы не поддерживаются
6. Входящие картинки — сегмент image (URL); отправка — URL / локальный путь
7. При истечении входа (просроченные cookie) адаптер пишет ошибки — повторите QR или обновите cookie

---

### Ссылки
- [Основной репозиторий ErisPulse](https://github.com/ErisPulse/ErisPulse/)
- [bilibili-api-python](https://github.com/Passkou/bilibili-api)
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)
- [Руководство по разработке модулей](https://www.erisdev.com/#docs/developer-guide/README.md)
