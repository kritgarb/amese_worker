import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# =========================
# Config & utilidades base
# =========================

# Detecta se está rodando como executável PyInstaller
def _get_root_dir():
    """
    Retorna o diretório raiz do projeto.
    Se rodando como executável PyInstaller, retorna o diretório onde o EXE está.
    Se rodando em desenvolvimento (python main.py), retorna o diretório do projeto.
    """
    if getattr(sys, 'frozen', False):
        # Rodando como executável PyInstaller
        # sys.executable é o caminho completo do EXE
        # Retorna o diretório onde o EXE está localizado
        return Path(sys.executable).parent
    else:
        # Rodando em desenvolvimento
        BASE_DIR = Path(__file__).resolve().parent  # src/
        return BASE_DIR.parent  # raiz do projeto

ROOT_DIR = _get_root_dir()
BASE_DIR = ROOT_DIR / "src" if not getattr(sys, 'frozen', False) else ROOT_DIR

# Debug: mostra informações sobre o ambiente de execução
_is_frozen = getattr(sys, 'frozen', False)


# Carrega variáveis de ambiente do arquivo .env
# No executável, procura .env no mesmo diretório do EXE
env_path = ROOT_DIR / ".env"

if env_path.exists():
    load_dotenv(env_path, override=True)


# Tenta carregar .env do diretório src também (para compatibilidade em desenvolvimento)
if not _is_frozen:
    src_env = BASE_DIR / ".env"
    if src_env.exists():
        load_dotenv(src_env, override=True)

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
# Usa caminho absoluto para FAILED_DIR (importante para rodar como serviço Windows)
_FAILED_DIR_DEFAULT = str(ROOT_DIR / "completo" / "failed_events")
FAILED_DIR       = os.getenv("FAILED_DIR", _FAILED_DIR_DEFAULT)

_TERCEIROS_RAW = os.getenv("TERCEIROS")
if _TERCEIROS_RAW:
    TERCEIROS = [t.strip() for t in _TERCEIROS_RAW.split(",") if t.strip()]
else:
    single = os.getenv("TERCEIRO", "DIAGNÓSTICO DO BRASIL - DB")
    TERCEIROS = [single] if single else []

TERCEIRO = TERCEIROS[0] if TERCEIROS else ""

# Filtro exclusivo para o telemed (exames de imagem).
# Se vazio, o telemed não recebe nada além do que já está em TERCEIROS.
_TELEMED_TERCEIROS_RAW = os.getenv("TELEMED_TERCEIROS")
TELEMED_TERCEIROS: list = (
    [t.strip() for t in _TELEMED_TERCEIROS_RAW.split(",") if t.strip()]
    if _TELEMED_TERCEIROS_RAW
    else []
)

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

# Mapeamento CodTExame -> CodigoExame para casos de integridade referencial quebrada
# Formato: "113:PIDIO,114:OUTRO,115:TESTE"
_CODTEXAME_MAP_RAW = os.getenv("CODTEXAME_MAP", "")
CODTEXAME_MAP: dict = {}
if _CODTEXAME_MAP_RAW:
    try:
        for pair in _CODTEXAME_MAP_RAW.split(","):
            if ":" in pair:
                cod_str, codigo_exame = pair.split(":", 1)
                cod_texame = int(cod_str.strip())
                CODTEXAME_MAP[cod_texame] = codigo_exame.strip()
    except Exception as e:
        print(f"Erro ao processar CODTEXAME_MAP: {e}")
        CODTEXAME_MAP = {}

# =========================
# Config Telemed (amese_telemed)
# =========================
TELEMED_URL   = os.getenv("TELEMED_URL", "").rstrip("/")   # ex: http://localhost:3000
TELEMED_TOKEN = os.getenv("TELEMED_TOKEN", "")             # deve coincidir com WORKER_SECRET no telemed
TELEMED_TIMEOUT = int(os.getenv("TELEMED_TIMEOUT", "15"))

# =========================
# Config Google Sheets
# =========================
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID")       # ID da planilha Google Sheets
GOOGLE_SHEET_RANGE = os.getenv("GOOGLE_SHEET_RANGE", "Sheet1!A:C")  # Range das colunas (padrão: Sheet1!A:C)
GOOGLE_API_KEY     = os.getenv("GOOGLE_API_KEY")        # API Key do Google Cloud
