import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
SPREADSHEET_ID: str = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS_JSON: str = os.environ["GOOGLE_CREDENTIALS_JSON"]
SHEET_NAME: str = os.getenv("SHEET_NAME", "Presupuesto")

_raw_ids = os.getenv("ALLOWED_CHAT_IDS", "")
ALLOWED_CHAT_IDS: list[int] = [int(x.strip()) for x in _raw_ids.split(",") if x.strip()]
