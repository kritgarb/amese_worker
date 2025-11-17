import os
from pathlib import Path

from dotenv import load_dotenv

# =========================
# Config & utilidades base
# =========================
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env", override=True)
load_dotenv(BASE_DIR / ".env", override=True)

# =========================
# Config do Banco
# =========================
SERVER = os.getenv("DB_SERVER", r"localhost\SQLEXPRESS")  # ex: localhost\SQLEXPRESS ou 10.0.0.5\SQLEXPRESS
DB     = os.getenv("DB_NAME", "Ame-se")
USER   = os.getenv("DB_USER")
PWD    = os.getenv("DB_PASS")
DRIVER = os.getenv("ODBC_DRIVER", "ODBC Driver 18 for SQL Server")

POLL_SECONDS     = int(os.getenv("POLL_SECONDS", "5"))
DEBOUNCE_SECONDS = int(os.getenv("DEBOUNCE_SECONDS", "0"))  # 0 desliga
FAILED_DIR       = os.getenv("FAILED_DIR", "completo/failed_events")

_TERCEIROS_RAW = os.getenv("TERCEIROS")
if _TERCEIROS_RAW:
    TERCEIROS = [t.strip() for t in _TERCEIROS_RAW.split(",") if t.strip()]
else:
    single = os.getenv("TERCEIRO", "DIAGNÓSTICO DO BRASIL - DB")
    TERCEIROS = [single] if single else []

TERCEIRO = TERCEIROS[0] if TERCEIROS else ""

os.makedirs(FAILED_DIR, exist_ok=True)

# =========================
# Config Bemsoft
# =========================
BASE_URL        = os.getenv("BEMSOFT_BASE_URL", "https://bemsoft.ws.wiselab.com.br")
REQS_ENDPOINT   = os.getenv("BEMSOFT_ENDPOINT", "/requests")
TOKEN           = os.getenv("BEMSOFT_TOKEN")
TIMEOUT         = int(os.getenv("BEMSOFT_TIMEOUT", "30"))
RETRIES_TOTAL   = int(os.getenv("BEMSOFT_RETRIES", "3"))
RETRIES_BACKOFF = float(os.getenv("BEMSOFT_BACKOFF", "0.5"))
VERIFY_TLS      = os.getenv("BEMSOFT_VERIFY", "1") != "0"
DRY_RUN         = os.getenv("BEMSOFT_DRY_RUN", "0") == "1"

DEFAULT_GENDER  = (os.getenv("DEFAULT_GENDER") or "").strip().upper()  # "M" ou "F"
DEFAULT_BIRTH   = os.getenv("DEFAULT_BIRTHDATE")  # "YYYY-MM-DD"

PHYSICIAN_NAME  = os.getenv("PHYSICIAN_NAME")      # opcional
PHYSICIAN_COUNC = os.getenv("PHYSICIAN_COUNCIL")   # ex "CRM"
PHYSICIAN_NUM   = os.getenv("PHYSICIAN_NUMBER")
PHYSICIAN_UF    = os.getenv("PHYSICIAN_UF")

_TEST_MAP_PATH  = os.getenv("BEMSOFT_TEST_MAP_PATH")

# =========================
# Config Google Sheets
# =========================
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID")       # ID da planilha Google Sheets
GOOGLE_SHEET_RANGE = os.getenv("GOOGLE_SHEET_RANGE", "Sheet1!A:C")  # Range das colunas (padrão: Sheet1!A:C)
GOOGLE_API_KEY     = os.getenv("GOOGLE_API_KEY")        # API Key do Google Cloud
