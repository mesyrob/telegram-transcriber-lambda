import os
import json
import requests
import boto3

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "")
AUTHORIZED_USERS = set(
    int(x) for x in os.environ.get("AUTHORIZED_USERS", "").split(",") if x.strip()
)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"

lambda_client = boto3.client("lambda")
FUNCTION_NAME = os.environ["AWS_LAMBDA_FUNCTION_NAME"]


def update_authorized_users():
    """Persist updated AUTHORIZED_USERS back into Lambda environment vars."""
    # Convert back into comma-separated string
    updated = ",".join(str(uid) for uid in AUTHORIZED_USERS)
    
    # Get current config
    response = lambda_client.get_function_configuration(FunctionName=FUNCTION_NAME)
    env_vars = response["Environment"]["Variables"]
    
    # Update
    env_vars["AUTHORIZED_USERS"] = updated

    lambda_client.update_function_configuration(
        FunctionName=FUNCTION_NAME,
        Environment={"Variables": env_vars}
    )


def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )


def transcribe_audio(media_path):
    """Transcribe audio from audio or video file using OpenAI API."""
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    # Determine mime type based on file extension
    if media_path.endswith('.mp4'):
        mime_type = "video/mp4"
        filename = "media.mp4"
    else:
        mime_type = "audio/ogg"
        filename = "audio.ogg"

    with open(media_path, "rb") as f:
        resp = requests.post(
            OPENAI_TRANSCRIBE_URL,
            headers=headers,
            data={"model": "gpt-4o-transcribe", "response_format": "text"},
            files={"file": (filename, f, mime_type)},
        )

    resp.raise_for_status()
    return resp.text.strip()


def lambda_handler(event, context):
    body = json.loads(event.get("body", "{}"))
    message = body.get("message")
    if not message:
        return {"statusCode": 200}

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text")

    # -----------------------------
    # 1. PASSWORD CHECK
    # -----------------------------
    if text and text.startswith("/start"):
        parts = text.strip().split()
        if len(parts) == 2 and parts[1] == BOT_PASSWORD:
            AUTHORIZED_USERS.add(chat_id)
            update_authorized_users()
            send_message(chat_id, "Access granted! 🎉 You can now transcribe audio.")
        else:
            send_message(chat_id, "Incorrect password ❌")
        return {"statusCode": 200}

    # -----------------------------
    # 2. BLOCK UNAUTHORIZED USERS
    # -----------------------------
    if chat_id not in AUTHORIZED_USERS:
        send_message(chat_id, "This bot is locked. Send the correct password using:\n/start <password>")
        return {"statusCode": 200}

    # -----------------------------
    # 3. HANDLE VOICE, AUDIO, OR VIDEO
    # -----------------------------
    voice = message.get("voice")
    audio = message.get("audio")
    video = message.get("video")
    video_note = message.get("video_note")

    if not (voice or audio or video or video_note):
        send_message(chat_id, "Send me a voice message, audio file, or video.")
        return {"statusCode": 200}

    # Get file_id from whichever type was sent
    if voice:
        file_id = voice["file_id"]
        file_extension = "ogg"
    elif audio:
        file_id = audio["file_id"]
        file_extension = "ogg"
    elif video:
        file_id = video["file_id"]
        file_extension = "mp4"
    else:  # video_note
        file_id = video_note["file_id"]
        file_extension = "mp4"

    # Get file path
    file_info = requests.get(
        f"{TELEGRAM_API}/getFile", params={"file_id": file_id}
    ).json()
    file_path = file_info["result"]["file_path"]

    # Download
    file_bytes = requests.get(
        f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    ).content

    media_path = f"/tmp/media.{file_extension}"
    with open(media_path, "wb") as f:
        f.write(file_bytes)

    # Transcribe (OpenAI API extracts audio from video automatically)
    try:
        transcript = transcribe_audio(media_path)
        send_message(chat_id, transcript)
    except Exception as e:
        print("transcription error:", e)
        send_message(chat_id, "Transcription failed 😔")

    return {"statusCode": 200}
