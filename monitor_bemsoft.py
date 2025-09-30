import os
import time
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal

# ======= Dependências HTTP e retries =======
import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ======= SQLAlchemy / DB =======
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

# ======= ENV =======
from dotenv import load_dotenv

# =========================
# Config & utilidades base
# =========================
BASE_DIR = os.path.dirname(__file__)
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH, override=True)

def json_dumps(obj, pretty: bool = False) -> str:
    def _default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        return str(o)
    if pretty:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=_default)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_default)

TZ_MACEIO = timezone(timedelta(hours=-3))

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
TERCEIRO         = os.getenv("TERCEIRO", "DIAGNÓSTICO DO BRASIL - DB")

os.makedirs(FAILED_DIR, exist_ok=True)

# Conexão robusta com instância nomeada via odbc_connect
raw_odbc = (
    f"DRIVER={DRIVER};"
    f"SERVER={SERVER};"                  # ex: localhost\\SQLEXPRESS
    f"DATABASE={DB};"
    f"UID={USER};PWD={PWD};"
    "Encrypt=yes;TrustServerCertificate=yes"
)
params = quote_plus(raw_odbc)
ENGINE = create_engine(
    f"mssql+pyodbc:///?odbc_connect={params}",
    poolclass=QueuePool, pool_pre_ping=True,
    pool_size=5, max_overflow=2, future=True
)

SQL_GET_LAST = text("""
SELECT LastItemId
FROM dbo._MonitorState WITH (UPDLOCK, ROWLOCK)
WHERE Name = 'ItemSolMonitor';
""")

SQL_SET_LAST = text("""
UPDATE dbo._MonitorState
   SET LastItemId = :last, UpdatedAt = SYSUTCDATETIME()
 WHERE Name = 'ItemSolMonitor';
""")

SQL_BOOTSTRAP = [
text("""
IF OBJECT_ID('dbo._MonitorState','U') IS NULL
BEGIN
  CREATE TABLE dbo._MonitorState (
    Name sysname NOT NULL PRIMARY KEY,
    LastItemId BIGINT NULL,
    UpdatedAt datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
  );
END;"""),
text("""
IF NOT EXISTS (SELECT 1 FROM dbo._MonitorState WHERE Name='ItemSolMonitor')
  INSERT INTO dbo._MonitorState (Name, LastItemId) VALUES ('ItemSolMonitor', 0);
""")
]

SQL_FETCH = text("""
SELECT TOP (500)
    i.CodItemSol, i.CodSolicitacao, i.DataEntrada, i.DescExames, i.CodConvExames,
    i.NomeTerceirizado, i.Valor, i.VlTerceirizado, i.SituacaoResultado, i.Origem,

    s.codpaciente, s.CodConvenio, s.dtaentrada AS Sol_dtaentrada, s.Hora, s.Valortotal, s.TipoPgto, s.Obs_Sol,

    p.nome AS PacienteNome, p.cpf AS PacienteCPF, p.datanasc AS PacienteNascimento,
    p.fone AS PacienteFone, p.EmailPac AS PacienteEmail, p.cidade AS PacienteCidade, p.uf AS PacienteUF,
    p.sexo AS PacienteSexo
FROM dbo.ItemSol i
JOIN dbo.solicitacao s ON s.codsolicitacao = i.CodSolicitacao
LEFT JOIN dbo.paciente p ON p.codpaciente = s.codpaciente
WHERE
    i.CodItemSol > :last
    AND i.NomeTerceirizado = :terceiro
ORDER BY i.CodItemSol ASC;
""")

def bootstrap_state():
    with ENGINE.begin() as conn:
        for q in SQL_BOOTSTRAP:
            conn.execute(q)

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
_TEST_MAP: Dict[str, str] = {}
if _TEST_MAP_PATH and os.path.isfile(_TEST_MAP_PATH):
    try:
        with open(_TEST_MAP_PATH, "r", encoding="utf-8") as f:
            _TEST_MAP = {str(k).strip().upper(): str(v).strip() for k, v in (json.load(f) or {}).items()}
    except Exception:
        _TEST_MAP = {}

def _only_digits(s: Optional[str]) -> Optional[str]:
    return "".join(ch for ch in (s or "") if ch.isdigit()) or None

def _split_iso(iso_val: Optional[Any]) -> Tuple[Optional[str], Optional[str]]:
    """Aceita string ISO ou datetime; retorna (YYYY-MM-DD, HH:MM:SS)"""
    if not iso_val:
        return None, None
    try:
        if isinstance(iso_val, datetime):
            dt = iso_val
        else:
            dt = datetime.fromisoformat(str(iso_val).replace("Z", "+00:00"))
    except Exception:
        return None, None
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")

def _choose_date_time(solicitacao: Dict[str, Any], itens: List[Dict[str, Any]]) -> Tuple[str, str]:
    dta = solicitacao.get("dtaentrada")
    hora = solicitacao.get("Hora")
    if dta:
        try:
            d = datetime.fromisoformat(str(dta).replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except Exception:
            d = None
        if d and hora:
            try:
                if isinstance(hora, str) and len(hora) == 5:
                    hora = hora + ":00"
                t = datetime.strptime(str(hora), "%H:%M:%S").strftime("%H:%M:%S")
                return d, t
            except Exception:
                pass
    for it in itens or []:
        d, t = _split_iso(it.get("DataEntrada"))
        if d and t:
            return d, t
    now = datetime.now(TZ_MACEIO)
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")

def _uuid() -> str:
    return str(uuid.uuid4())

def _idemp_key(codsol: Any) -> str:
    return f"sol-{codsol}" if codsol is not None else f"sol-{_uuid()}"

def map_support_test(local_code: Optional[str]) -> Optional[str]:
    if not local_code:
        return None
    key = str(local_code).strip()
    if not key:
        return None
    mapped = _TEST_MAP.get(key.upper())
    return mapped or key

def _build_session() -> Session:
    s = requests.Session()
    s.verify = VERIFY_TLS
    retries = Retry(
        total=RETRIES_TOTAL,
        backoff_factor=RETRIES_BACKOFF,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

# ===== Cache de /tests =====
class TestsIndex:
    def __init__(self, base_url: str, token: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.cache: Dict[str, Dict[str, Any]] = {}

    def ensure_loaded(self, session: Session):
        if self.cache:
            return
        url = f"{self.base_url}/tests"
        resp = session.get(url, headers={"Authorization": f"Bearer {self.token}"}, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Falha ao carregar /tests ({resp.status_code}): {resp.text}")
        data = resp.json() or {}
        for t in (data.get("tests") or []):
            tid = (t.get("id") or "").strip()
            if not tid:
                continue
            specimen_id = (t.get("specimen", {}) or {}).get("id")
            self.cache[tid] = {"name": t.get("name"), "specimen_id": specimen_id}

    def specimen_for(self, session: Session, support_test_id: Optional[str]) -> Optional[str]:
        if not support_test_id:
            return None
        self.ensure_loaded(session)
        entry = self.cache.get(support_test_id)
        return entry.get("specimen_id") if entry else None

_TESTS_INDEX: Optional[TestsIndex] = None
def _get_tests_index() -> TestsIndex:
    global _TESTS_INDEX
    if _TESTS_INDEX is None:
        if not TOKEN and not DRY_RUN:
            raise RuntimeError("BEMSOFT_TOKEN não configurado para consultar /tests")
        _TESTS_INDEX = TestsIndex(BASE_URL, TOKEN or "", TIMEOUT)
    return _TESTS_INDEX

# =========================
# Transformação p/ Bemsoft
# =========================
def build_payload(event: Dict[str, Any], session: Optional[Session] = None) -> Dict[str, Any]:
    solicitacao = event.get("solicitacao", {}) or {}
    paciente    = event.get("paciente", {}) or {}
    itens       = event.get("itens", []) or []

    codsol   = solicitacao.get("codsolicitacao")
    batch_id = f"sol-{codsol}" if codsol is not None else f"sol-{_uuid()}"
    order_id = f"order-{codsol}" if codsol is not None else f"order-{_uuid()}"
    bdate, btime = _choose_date_time(solicitacao, itens)

    # patient.externalId
    if paciente.get("codpaciente") is not None:
        pat_ext = f"pat-{paciente['codpaciente']}"
    elif paciente.get("cpf"):
        pat_ext = f"cpf-{_only_digits(paciente['cpf'])}"
    else:
        pat_ext = f"pat-{_uuid()}"

    # birthDate
    birth_date: Optional[str] = None
    if paciente.get("datanasc"):
        try:
            bd = datetime.fromisoformat(str(paciente["datanasc"]).replace("Z", "+00:00"))
            birth_date = bd.strftime("%Y-%m-%d")
        except Exception:
            pass
    if not birth_date:
        birth_date = DEFAULT_BIRTH
    if not birth_date:
        raise ValueError("birthDate obrigatório e não encontrado (defina DEFAULT_BIRTHDATE no .env).")

    # gender
    gender = (paciente.get("sexo") or paciente.get("PacienteSexo") or "").strip().upper() or (DEFAULT_GENDER or "")
    if gender not in {"M", "F"}:
        raise ValueError("gender obrigatório ausente/ inválido (defina paciente.sexo ou DEFAULT_GENDER='M'|'F' no .env).")

    # physician opcional
    physician = None
    if PHYSICIAN_NAME and PHYSICIAN_COUNC and PHYSICIAN_NUM and PHYSICIAN_UF:
        physician = {
            "externalId": PHYSICIAN_NUM,
            "name": PHYSICIAN_NAME,
            "councilAbbreviation": PHYSICIAN_COUNC,
            "councilNumber": PHYSICIAN_NUM,
            "councilUf": PHYSICIAN_UF,
        }

    sess = session or (_build_session() if not DRY_RUN else None)
    tests_index: Optional[TestsIndex] = None if DRY_RUN else _get_tests_index()

    tests: List[Dict[str, Any]] = []
    for it in itens:
        item_ext = f"item-{it.get('CodItemSol') or _uuid()}"
        d_col, t_col = _split_iso(it.get("DataEntrada"))
        d_col = d_col or bdate
        t_col = t_col or btime

        support_test_id = map_support_test(it.get("CodigoExame"))
        if not support_test_id:
            support_test_id = (it.get("CodigoExame") or "").strip()

        if DRY_RUN:
            specimen_id = "SPECIMEN-TEST"
        else:
            specimen_id = tests_index.specimen_for(sess, support_test_id)  # type: ignore
            if not specimen_id:
                raise ValueError(
                    f"supportSpecimenId ausente para supportTestId='{support_test_id}'. "
                    f"Ajuste o mapping (BEMSOFT_TEST_MAP_PATH) ou o catálogo /tests."
                )

        tests.append({
            "externalId": item_ext,
            "collectionDate": d_col,
            "collectionTime": t_col,
            "supportTestId": support_test_id,
            "supportSpecimenId": specimen_id,
            "additionalInformations": [
                {"key": "origem", "value": it.get("Origem") or "API"},
                {"key": "descricao", "value": it.get("DescExames") or ""},
            ],
            "condition": None,
            "preservative": None,
            "diuresisVolume": None,
            "diuresisTime": None,
        })

    payload = {
        "batch": {
            "externalId": batch_id,
            "date": bdate,
            "time": btime,
            "order": {
                "externalId": order_id,
                "date": bdate,
                "time": btime,
                "patientHeight": None,
                "patientWeight": None,
                "patient": {
                    "externalId": pat_ext,
                    "name": paciente.get("nome") or "NOME_NAO_INFORMADO",
                    "birthDate": birth_date,
                    "gender": gender,
                    "weight": None,
                    "height": None,
                },
                "physician": physician,
                "tests": tests,
            }
        }
    }
    return payload

def send_to_bemsoft(event: Dict[str, Any], session: Optional[Session] = None) -> Dict[str, Any]:
    """Transforma e envia POST /requests (ou apenas gera no DRY_RUN)."""
    if DRY_RUN:
        payload = build_payload(event, session=None)
        print("[bemsoft] DRY_RUN ativo. Payload gerado, não enviado.")
        return {"ok": True, "status": 200, "data": {"dryRun": True, "payload": payload}}

    if not TOKEN:
        return {"ok": False, "status": 401, "error": "BEMSOFT_TOKEN não configurado (Bearer)"}

    sess = session or _build_session()
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Idempotency-Key": _idemp_key(event.get("solicitacao", {}).get("codsolicitacao")),
    }
    url = BASE_URL.rstrip("/") + REQS_ENDPOINT
    payload = build_payload(event, session=sess)

    resp = sess.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    status = resp.status_code
    try:
        body = resp.json() if resp.content else None
    except Exception:
        body = resp.text

    if 200 <= status < 300:
        return {"ok": True, "status": status, "data": body}
    if status == 409:  # idempotência
        return {"ok": True, "status": status, "data": body, "idempotent": True}
    return {"ok": False, "status": status, "error": body}

# =========================
# Monitor: transform + send
# =========================
def persist_failed(event: Dict[str, Any], reason: str = ""):
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    key = event.get("solicitacao", {}).get("codsolicitacao", "unknown")
    path = os.path.join(FAILED_DIR, f"{ts}_{key}.json")
    data = {"reason": reason, "event": event}
    with open(path, "w", encoding="utf-8") as f:
        f.write(json_dumps(data, pretty=True))
    print(f"[fail] salvo para retry manual: {path}")

def row_to_item(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "CodItemSol": r["CodItemSol"],
        "DataEntrada": r["DataEntrada"],
        "DescExames": r["DescExames"],
        "CodigoExame": r["CodConvExames"],
        "NomeTerceirizado": r["NomeTerceirizado"],
        "Valor": r["Valor"],
        "VlTerceirizado": r["VlTerceirizado"],
        "SituacaoResultado": r["SituacaoResultado"],
        "Origem": r["Origem"],
    }

def build_group_event(head_row: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
    solicitacao = {
        "codsolicitacao": head_row["CodSolicitacao"],
        "codpaciente": head_row["codpaciente"],
        "CodConvenio": head_row["CodConvenio"],
        "dtaentrada": head_row["Sol_dtaentrada"],
        "Hora": head_row["Hora"],
        "Valortotal": head_row["Valortotal"],
        "TipoPgto": head_row["TipoPgto"],
        "Obs_Sol": head_row["Obs_Sol"],
    }
    paciente = {
        "nome": head_row["PacienteNome"],
        "cpf": head_row["PacienteCPF"],
        "datanasc": head_row["PacienteNascimento"],
        "fone": head_row["PacienteFone"],
        "email": head_row["PacienteEmail"],
        "cidade": head_row["PacienteCidade"],
        "uf": head_row["PacienteUF"],
        "sexo": head_row.get("PacienteSexo"),
        "codpaciente": head_row.get("codpaciente"),
    }
    return {"solicitacao": solicitacao, "paciente": paciente, "itens": items}

def poll_once(sess_http: Optional[Session]) -> int:
    """Lê last_id, busca novos itens, debounce, agrupa por solicitação e envia 1 payload por grupo."""
    with ENGINE.begin() as conn:
        last = conn.execute(SQL_GET_LAST).scalar() or 0
        rows = conn.execute(SQL_FETCH, {"last": last, "terceiro": TERCEIRO}).mappings().all()
        if not rows:
            return last

        # Debounce: evita pegar solicitação incompleta
        if DEBOUNCE_SECONDS > 0:
            cutoff = datetime.utcnow().timestamp() - DEBOUNCE_SECONDS
            def ts_ok(dt):
                try:
                    return (dt.timestamp() <= cutoff) if isinstance(dt, datetime) else True
                except Exception:
                    return True
            rows = [r for r in rows if ts_ok(r["DataEntrada"])]
            if not rows:
                return last

        # Agrupa por solicitação
        groups: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            k = r["CodSolicitacao"]
            if k not in groups:
                groups[k] = {"head": r, "items": []}
            groups[k]["items"].append(row_to_item(r))

        new_last = last
        for cod, g in groups.items():
            event = build_group_event(g["head"], g["items"])
            print(f"\n== SOLICITAÇÃO {cod} | itens={len(g['items'])} ==\n{json_dumps(event, pretty=True)}\n")
            try:
                result = send_to_bemsoft(event, session=sess_http)
                ok = result.get("ok")
                status = result.get("status")
                if ok:
                    print(f"[bemsoft] entregue com sucesso (status={status}).")
                else:
                    print(f"[bemsoft] erro (status={status}): {result.get('error')}")
                    persist_failed(event, reason=f"HTTP {status}: {result.get('error')}")
            except Exception as e:
                print(f"[bemsoft] exceção ao enviar: {e}")
                persist_failed(event, reason=str(e))

            group_max = max(i["CodItemSol"] for i in g["items"])
            new_last = max(new_last, group_max)

        conn.execute(SQL_SET_LAST, {"last": new_last})
        return new_last

def main():
    print("Monitor ItemSol -> Bemsoft iniciado.")
    print(f"Filtro TERCEIRO='{TERCEIRO}' | Poll={POLL_SECONDS}s | Debounce={DEBOUNCE_SECONDS}s | DRY_RUN={DRY_RUN}")
    if not DRY_RUN and not TOKEN:
        print("[warn] BEMSOFT_TOKEN ausente. Ative DRY_RUN=1 ou configure o token.")
    # Bootstrap estado
    bootstrap_state()
    # Sessão HTTP única (reuso/keep-alive)
    sess_http = _build_session() if not DRY_RUN else None

    try:
        while True:
            try:
                poll_once(sess_http)
            except Exception as e:
                print(f"[ERRO] ciclo falhou: {e}")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nEncerrado pelo usuário.")

if __name__ == "__main__":
    main()
