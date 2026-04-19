import os
import json
import requests
from pathlib import Path
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# ── Конфіги з GitHub Secrets ──────────────────────────────────────────
ANTHROPIC_API_KEY     = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID   = os.environ["TELEGRAM_CHANNEL_ID"]
GOOGLE_DRIVE_FOLDER_ID= os.environ["GOOGLE_DRIVE_FOLDER_ID"]
GOOGLE_CREDENTIALS    = os.environ["GOOGLE_CREDENTIALS"]

# ── Файл стану ─────────────────────────────────────────────────────────
STATE_FILE = "state.json"

def load_state():
    if Path(STATE_FILE).exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"index": 0}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ── Google Drive ────────────────────────────────────────────────────────
def get_drive_photos():
    creds_info = json.loads(GOOGLE_CREDENTIALS)
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    service = build("drive", "v3", credentials=creds)
    results = service.files().list(
        q=f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed=false",
        orderBy="name",
        fields="files(id, name)"
    ).execute()
    return results.get("files", [])

def download_photo(file_id):
    creds_info = json.loads(GOOGLE_CREDENTIALS)
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    service = build("drive", "v3", credentials=creds)
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()

# ── Anthropic ───────────────────────────────────────────────────────────
def generate_caption(filename):
    hint = filename.replace("_", " ").replace("-", " ").rsplit(".", 1)[0]

    prompt = f"""Ти — менеджер автомайстерні BimmerGarage у Ковелі, яка спеціалізується на BMW F-серії.
Напиши короткий пост (3-5 речень) українською мовою для соціальних мереж до фото запчастини або автомобіля BMW.
Назва файлу для контексту: {hint}

Вимоги:
- Живий, невимушений тон, ніби пишеш від себе
- Згадай BimmerGarage або Ковель природньо
- Без хештегів, без емодзі на початку, максимум 1-2 емодзі в тексті
- В кінці додай: "📍 Ковель | BimmerGarage | t.me/bimmergarage"
- Кожен раз інший текст, не повторюйся

Відповідай ТІЛЬКИ текстом посту, без пояснень."""

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    data = response.json()
    return data["content"][0]["text"].strip()

# ── Telegram ────────────────────────────────────────────────────────────
def post_telegram(photo_bytes, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    response = requests.post(url, data={
        "chat_id": TELEGRAM_CHANNEL_ID,
        "caption": caption
    }, files={"photo": ("photo.jpg", photo_bytes, "image/jpeg")})
    print(f"Telegram: {response.status_code} {response.text[:200]}")
    return response.ok

# ── Головна функція ─────────────────────────────────────────────────────
def main():
    print(f"Запуск BimmerGarage autopost — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    photos = get_drive_photos()
    if not photos:
        print("Фото в Google Drive не знайдено")
        return

    print(f"Знайдено фото: {len(photos)}")

    state = load_state()
    index = state["index"] % len(photos)
    photo = photos[index]

    print(f"Фото #{index + 1}: {photo['name']}")

    photo_bytes = download_photo(photo["id"])
    caption = generate_caption(photo["name"])

    print(f"Опис: {caption}")

    post_telegram(photo_bytes, caption)

    state["index"] = index + 1
    save_state(state)
    print("Готово!")

if __name__ == "__main__":
    main()
