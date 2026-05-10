# TG Music Bot for DJs 🎧

**TG Music Bot** — Telegram-бот для диджеев на **Python 3.11+** и **aiogram 3**. Скачивает треки со стриминговых платформ в высоком качестве.

**Поддерживаемые платформы:**
- YouTube / YouTube Music
- SoundCloud  
- Spotify
- Яндекс.Музыка
- Bandcamp
- Прямые ссылки на аудиофайлы (.mp3, .flac, .wav)

Треки сохраняются в SQLite + отправляются в чат с метаданными (название, исполнитель).

Дополнительно: веб-интерфейс на FastAPI для управления библиотекой.

## Структура

- `bot/` — точка входа, хендлеры команд и ссылок, middleware с зависимостями
- `services/` — проверка URL, HTTP-загрузка с лимитами и таймаутами
- `storage/` — SQLite (история, статусы, метаданные)
- `utils/` — настройки из `.env`, логирование
- `admin/` — FastAPI + Jinja2 (дашборд)

## Установка (локально)

Требуется **Python 3.11+**.

```bash
cd telegram_music_library_bot
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Отредактируйте .env: укажите BOT_TOKEN
```

Запуск бота (рабочая директория — корень проекта):

```bash
export PYTHONPATH="$(pwd)"
python -m bot.main
```

Запуск админки:

```bash
export PYTHONPATH="$(pwd)"
uvicorn admin.app:app --host 0.0.0.0 --port 8080
```

Откройте в браузере `http://127.0.0.1:8080/`. Если задан `ADMIN_SECRET`, добавьте `?token=<секрет>` или заголовок `X-Admin-Token`.

## Docker

```bash
cp .env.example .env
# В .env для контейнеров задайте пути, например:
# DATABASE_PATH=/app/data/library.db
# DOWNLOAD_DIR=/app/downloads

docker compose up --build -d
```

- Бот: сервис `bot`
- Админка: сервис `admin`, порт хоста из переменной окружения `ADMIN_PORT` (по умолчанию `8080` → проброс на `8080` контейнера)

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|----------------|
| `BOT_TOKEN` | Токен от [@BotFather](https://t.me/BotFather) | пусто (для **бота** обязателен; для отдельного запуска только админки можно не задавать) |
| `DATABASE_PATH` | Путь к SQLite | `./data/library.db` |
| `DOWNLOAD_DIR` | Каталог загрузок | `./downloads` |
| `MAX_FILE_MB` | Максимальный размер файла | `50` |
| `DOWNLOAD_TIMEOUT_SEC` | Таймаут чтения при GET | `120` |
| `HTTP_HEAD_TIMEOUT_SEC` | Таймаут на соединение для HEAD | `15` |
| `ALLOWED_HOSTS` | Список разрешённых хостов через запятую (пусто — любой хост при прочих проверках) | пусто |
| `ADMIN_HOST` / `ADMIN_PORT` | Параметры для локального `uvicorn` (не для compose порта хоста) | `0.0.0.0` / `8080` |
| `ADMIN_SECRET` | Опциональная защита веб-интерфейса и API | пусто |

## Поведение ссылок

### Стриминговые платформы (YouTube, SoundCloud, Spotify, Яндекс.Музыка)
- Используется **yt-dlp** для скачивания аудио в лучшем качестве
- Конвертация в MP3 с максимальным битрейтом
- Извлекаются метаданные: название трека, исполнитель, длительность
- Ограничение по размеру: `MAX_FILE_MB`

### Прямые ссылки
1. Проверяется схема `http`/`https` и домен
2. Если `ALLOWED_HOSTS` не пустой, хост должен входить в список
3. Загрузка выполняется если ресурс похож на прямой аудиофайл: известное расширение (`.mp3`, `.flac`, …) и/или заголовок `Content-Type` с префиксом `audio/`
4. Учитываются `Content-Length` и фактический размер — не больше `MAX_FILE_MB`

## Команды бота

- `/start`, `/help` — описание
- `/add <url>` — добавить ссылку и попытаться скачать
- Отправка **только URL** текстом — то же, что `/add`
- `/list` — последние записи пользователя
- `/delete <id>` — удалить запись и файл на диске (если был)
- `/status` — краткая статистика по вашим записям

## Пример использования

1. Создай бота в [@BotFather](https://t.me/BotFather), вставь токен в `.env`
2. Установи зависимости: `pip install -r requirements.txt`
3. Запусти бота: `python -m bot.main`
4. Отправь ссылку на трек:
   - SoundCloud: `https://soundcloud.com/artist/track-name`
   - YouTube: `https://youtube.com/watch?v=...`
   - Яндекс.Музыка: `https://music.yandex.ru/album/12345/track/67890`
   - Или просто: `/add <ссылка>`
5. Бот скачает аудио в MP3 (макс. качество) и пришлёт с метаданными
6. Открой админку для управления библиотекой

## API админки

- `GET /api/queue` — JSON очереди (`pending`, `downloading`)
- `GET /api/tracks` — JSON последних треков  

При включённом `ADMIN_SECRET` передайте `?token=` или `X-Admin-Token`.

## Лицензия и ответственность

TG Music bot предназначен для работы **только с URL, на которые у вас есть право доступа**. Не используйте его для обхода ограничений правообладателей или сервисов.
