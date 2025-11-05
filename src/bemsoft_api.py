import os
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date, timezone, timedelta

import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

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
        if not config.TOKEN and not config.DRY_RUN:
            raise RuntimeError("BEMSOFT_TOKEN não configurado para consultar /tests")
        _TESTS_INDEX = TestsIndex(config.BASE_URL, config.TOKEN or "", config.TIMEOUT)
    return _TESTS_INDEX

_TEST_MAP: Dict[str, str] = {}
if config._TEST_MAP_PATH and os.path.isfile(config._TEST_MAP_PATH):
    try:
        with open(config._TEST_MAP_PATH, "r", encoding="utf-8") as f:
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
    now = datetime.now(timezone(timedelta(hours=-3)))
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
    s.verify = config.VERIFY_TLS
    retries = Retry(
        total=config.RETRIES_TOTAL,
        backoff_factor=config.RETRIES_BACKOFF,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

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
        birth_date = config.DEFAULT_BIRTH
    if not birth_date:
        raise ValueError("birthDate obrigatório e não encontrado (defina DEFAULT_BIRTHDATE no .env).")

    # gender
    gender_raw = (paciente.get("sexo") or paciente.get("PacienteSexo") or "").strip().upper()
    if gender_raw == "MASCULINO":
        gender = "M"
    elif gender_raw == "FEMININO":
        gender = "F"
    else:
        gender = gender_raw

    if gender not in {"M", "F"}:
        gender = (config.DEFAULT_GENDER or "").strip().upper()

    if gender not in {"M", "F"}:
        raise ValueError("gender obrigatório ausente/ inválido (defina paciente.sexo ou DEFAULT_GENDER='M'|'F' no .env).")

    # physician opcional
    physician = None
    if config.PHYSICIAN_NAME and config.PHYSICIAN_COUNC and config.PHYSICIAN_NUM and config.PHYSICIAN_UF:
        physician = {
            "externalId": config.PHYSICIAN_NUM,
            "name": config.PHYSICIAN_NAME,
            "councilAbbreviation": config.PHYSICIAN_COUNC,
            "councilNumber": config.PHYSICIAN_NUM,
            "councilUf": config.PHYSICIAN_UF,
        }

    sess = session or (_build_session() if not config.DRY_RUN else None)
    tests_index: Optional[TestsIndex] = None if config.DRY_RUN else _get_tests_index()

    tests: List[Dict[str, Any]] = []
    for it in itens:
        item_ext = f"item-{it.get('CodItemSol') or _uuid()}"
        d_col, t_col = _split_iso(it.get("DataEntrada"))
        d_col = d_col or bdate
        t_col = t_col or btime

        support_test_id = map_support_test(it.get("CodigoExame"))
        if not support_test_id:
            support_test_id = (it.get("CodigoExame") or "").strip()

        if config.DRY_RUN:
            specimen_id = "SPECIMEN-TEST"
        else:
            specimen_id = tests_index.specimen_for(sess, support_test_id)
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
                {"key": "observacao_codigo_exame", "value": it.get("ExameDescricao") or ""},
            ],
            "condition": "",
            "preservative": "",
            "diuresisVolume": 0,
            "diuresisTime": 0,
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
                "patientHeight": 0,
                "patientWeight": 0,
                "patient": {
                    "externalId": pat_ext,
                    "name": paciente.get("nome") or "NOME_NAO_INFORMADO",
                    "birthDate": birth_date,
                    "gender": gender,
                    "weight": 0,
                    "height": 0,
                },
                "physician": physician,
                "tests": tests,
            }
        }
    }
    return payload

def send_to_bemsoft(event: Dict[str, Any], session: Optional[Session] = None, print_payload: bool = False) -> Dict[str, Any]:
    """Transforma e envia POST /requests (ou apenas gera no DRY_RUN)."""
    if config.DRY_RUN:
        payload_start = datetime.now()
        payload = build_payload(event, session=None)
        payload_end = datetime.now()
        payload_duration = (payload_end - payload_start).total_seconds()
        print(f"[{payload_end.strftime('%Y-%m-%d %H:%M:%S')}] [bemsoft] DRY_RUN ativo. Payload gerado em {payload_duration:.2f}s, não enviado.")
        if print_payload:
            import json
            print(f"\n== PAYLOAD ENVIADO ==\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n")
        return {"ok": True, "status": 200, "data": {"dryRun": True, "payload": payload}}

    if not config.TOKEN:
        return {"ok": False, "status": 401, "error": "BEMSOFT_TOKEN não configurado (Bearer)"}

    sess = session or _build_session()
    headers = {
        "Authorization": f"Bearer {config.TOKEN}",
        "Content-Type": "application/json",
        "Idempotency-Key": _idemp_key(event.get("solicitacao", {}).get("codsolicitacao")),
    }
    url = config.BASE_URL.rstrip("/") + config.REQS_ENDPOINT

    payload_start = datetime.now()
    payload = build_payload(event, session=sess)
    payload_end = datetime.now()
    payload_duration = (payload_end - payload_start).total_seconds()
    print(f"[{payload_end.strftime('%Y-%m-%d %H:%M:%S')}] [bemsoft] Payload construído em {payload_duration:.2f}s")

    if print_payload:
        import json as json_module
        print(f"\n== PAYLOAD ENVIADO ==\n{json_module.dumps(payload, ensure_ascii=False, indent=2)}\n")

    request_start = datetime.now()
    resp = sess.post(url, json=payload, headers=headers, timeout=config.TIMEOUT)
    request_end = datetime.now()
    request_duration = (request_end - request_start).total_seconds()
    print(f"[{request_end.strftime('%Y-%m-%d %H:%M:%S')}] [bemsoft] Request HTTP concluído em {request_duration:.2f}s")

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
