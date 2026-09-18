import os
import json
import time
import uuid
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date, timezone, timedelta

import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config
import sheets_client
import logger_txt

# ===== Cache de /tests =====
class TestsIndex:
    def __init__(self, base_url: str, token: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        # Cache armazena lista de variantes para cada test_id
        # {test_id: [{"name": "...", "specimen_id": "...", "specimen_name": "..."}, ...]}
        self.cache: Dict[str, List[Dict[str, Any]]] = {}
        self.loaded_at: Optional[float] = None      # quando o catalogo foi carregado
        self.last_refresh_try: Optional[float] = None

    def _expirado(self) -> bool:
        if self.loaded_at is None:
            return True
        if config.TESTS_TTL <= 0:
            return False
        return (time.time() - self.loaded_at) >= config.TESTS_TTL

    def ensure_loaded(self, session: Session, force: bool = False):
        """
        Carrega o catalogo /tests. Recarrega quando expira o TTL ou quando forcado.

        O cache antigo so e substituido se a nova leitura der certo — uma falha
        momentanea no Bemsoft nao pode zerar um catalogo que estava bom.
        """
        if self.cache and not force and not self._expirado():
            return

        self.last_refresh_try = time.time()
        url = f"{self.base_url}/tests"
        try:
            resp = session.get(url, headers={"Authorization": f"Bearer {self.token}"}, timeout=self.timeout)
        except Exception as e:
            if self.cache:
                print(f"[tests] falha ao recarregar catalogo ({e}); mantendo o cache anterior.")
                return
            raise

        if resp.status_code != 200:
            if self.cache:
                print(f"[tests] falha ao recarregar catalogo (HTTP {resp.status_code}); mantendo o cache anterior.")
                return
            raise RuntimeError(f"Falha ao carregar /tests ({resp.status_code}): {resp.text}")

        data = resp.json() or {}
        novo: Dict[str, List[Dict[str, Any]]] = {}
        for t in (data.get("tests") or []):
            tid = (t.get("id") or "").strip()
            if not tid:
                continue
            specimen = t.get("specimen", {}) or {}
            novo.setdefault(tid, []).append({
                "name": t.get("name"),
                "specimen_id": specimen.get("id"),
                "specimen_name": specimen.get("name"),
            })

        anterior = set(self.cache)
        self.cache = novo
        self.loaded_at = time.time()

        novos_ids = set(novo) - anterior
        if anterior and novos_ids:
            print(f"[tests] catalogo recarregado: {len(novo)} codigo(s), "
                  f"{len(novos_ids)} novo(s) desde a ultima leitura.")
        else:
            print(f"[tests] catalogo carregado: {len(novo)} codigo(s) distinto(s).")

    def specimen_for(self, session: Session, support_test_id: Optional[str], descmat_hint: Optional[str] = None) -> Optional[str]:
        """
        Retorna specimen_id para um test_id.
        Se descmat_hint for fornecido e houver múltiplas variantes, tenta matching por nome do material.
        """
        if not support_test_id:
            return None
        self.ensure_loaded(session)
        variants = self.cache.get(support_test_id)

        if not variants:
            # Codigo desconhecido: pode ter acabado de ser cadastrado no Bemsoft.
            # Releitura imediata do catalogo, limitada por TESTS_MIN_REFRESH para
            # nao disparar um GET /tests a cada item de um codigo realmente inexistente.
            agora = time.time()
            pode_tentar = (
                self.last_refresh_try is None
                or (agora - self.last_refresh_try) >= config.TESTS_MIN_REFRESH
            )
            if pode_tentar:
                print(f"[tests] '{support_test_id}' ausente do cache — recarregando catalogo...")
                self.ensure_loaded(session, force=True)
                variants = self.cache.get(support_test_id)
                if variants:
                    print(f"[tests] '{support_test_id}' encontrado após recarga do catálogo.")
            if not variants:
                return None

        # Se só há uma variante, retorna direto
        if len(variants) == 1:
            return variants[0].get("specimen_id")

        # Se há múltiplas variantes e temos hint do DESCMAT, tenta matching
        if descmat_hint:
            # Normaliza o hint: remove prefixos numéricos e pontos (ex: "0.Soro" -> "soro")
            hint_normalized = descmat_hint.lower().strip()
            # Remove padrão "número.palavra" -> "palavra"
            if '.' in hint_normalized:
                parts = hint_normalized.split('.', 1)
                if parts[0].isdigit():
                    hint_normalized = parts[1].strip()

            for variant in variants:
                specimen_name = (variant.get("specimen_name") or "").lower().strip()
                # Verifica se o nome do specimen aparece no DESCMAT OU vice-versa
                if specimen_name and (specimen_name in hint_normalized or hint_normalized in specimen_name):
                    print(f"[tests] Match encontrado para '{support_test_id}': specimen '{specimen_name}' matches DESCMAT '{descmat_hint}' (normalizado: '{hint_normalized}')")
                    return variant.get("specimen_id")

        # Se não encontrou match ou não tem hint, usa a primeira variante e avisa
        print(f"[tests] Aviso: '{support_test_id}' tem {len(variants)} variantes. Usando primeira: {variants[0].get('name')} (specimen: {variants[0].get('specimen_name')})")
        return variants[0].get("specimen_id")

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

def _itens_fingerprint(itens: List[Dict[str, Any]]) -> str:
    """
    Hash curto do conjunto exato de itens do payload.

    Usado na Idempotency-Key e nos externalId. Sem isso, uma solicitacao que
    recebe exames novos depois de ja ter sido enviada reusaria a mesma chave,
    o Bemsoft devolveria 409 e os exames acrescentados seriam descartados em
    silencio.
    """
    ids = ",".join(
        str(i.get("CodItemSol"))
        for i in sorted(itens or [], key=lambda x: (x.get("CodItemSol") is None, x.get("CodItemSol")))
    )
    return hashlib.sha1(ids.encode("utf-8")).hexdigest()[:12]


def _idemp_key(codsol: Any, itens: Optional[List[Dict[str, Any]]] = None) -> str:
    base = f"sol-{codsol}" if codsol is not None else f"sol-{_uuid()}"
    if itens:
        return f"{base}-{_itens_fingerprint(itens)}"
    return base

def map_support_test(local_code: Optional[str]) -> Optional[str]:
    if not local_code:
        return None
    key = str(local_code).strip()
    if not key:
        return None
    mapped = _TEST_MAP.get(key.upper())
    return mapped or key

def _erro_no_corpo(body: Any) -> Optional[str]:
    """
    O WiseLab pode responder HTTP 201 com um erro no corpo, por exemplo:
        201 {"error": "Nao foi possivel salvar os dados recebidos no lote sol-X."}
    Tratar 201 como sucesso cego fazia o worker dar o lote por entregue enquanto
    nada era gravado. Qualquer campo de erro preenchido invalida o sucesso.
    """
    if isinstance(body, dict):
        for chave in ("error", "errors", "erro", "erros", "message_error", "mensagemErro"):
            valor = body.get(chave)
            if valor:
                return str(valor)
    return None


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

def build_payload(event: Dict[str, Any], session: Optional[Session] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Monta o payload do Bemsoft.

    Retorna (payload, rejeitados). Itens que nao resolvem supportSpecimenId sao
    separados em `rejeitados` em vez de abortarem a requisicao inteira: o restante
    da solicitacao segue normalmente e os rejeitados vao para o log .txt.
    `payload` vem None quando nenhum item sobrou.
    """
    solicitacao = event.get("solicitacao", {}) or {}
    paciente    = event.get("paciente", {}) or {}
    itens       = event.get("itens", []) or []

    codsol   = solicitacao.get("codsolicitacao")
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

    # physician opcional - se não tiver dados completos, não inclui no payload
    physician_data = None
    if config.PHYSICIAN_NAME and config.PHYSICIAN_COUNC and config.PHYSICIAN_NUM and config.PHYSICIAN_UF:
        physician_data = {
            "externalId": config.PHYSICIAN_NUM,
            "name": config.PHYSICIAN_NAME,
            "councilAbbreviation": config.PHYSICIAN_COUNC,
            "councilNumber": config.PHYSICIAN_NUM,
            "councilUf": config.PHYSICIAN_UF,
        }

    sess = session or (_build_session() if not config.DRY_RUN else None)
    tests_index: Optional[TestsIndex] = None if config.DRY_RUN else _get_tests_index()

    tests: List[Dict[str, Any]] = []
    rejeitados: List[Dict[str, Any]] = []
    aceitos: List[Dict[str, Any]] = []
    for it in itens:
        item_ext = f"item-{it.get('CodItemSol') or _uuid()}"
        d_col, t_col = _split_iso(it.get("DataEntrada"))
        d_col = d_col or bdate
        t_col = t_col or btime

        support_test_id = map_support_test(it.get("CodigoExame"))
        if not support_test_id:
            support_test_id = (it.get("CodigoExame") or "").strip()

        # Busca informações do Google Sheets ANTES de resolver specimen_id
        test_info = sheets_client.get_test_info(support_test_id)
        descmat = test_info.get("SUPPORT_LAB_DESCMAT") if test_info else None

        print(f"[debug] support_test_id='{support_test_id}', test_info={test_info}, descmat='{descmat}'")

        if config.DRY_RUN:
            specimen_id = "SPECIMEN-TEST"
        else:
            # Passa descmat como hint para resolver ambiguidade de múltiplas variantes
            specimen_id = tests_index.specimen_for(sess, support_test_id, descmat_hint=descmat)
            print(f"[debug] specimen_id retornado: '{specimen_id}'")
            if not specimen_id:
                motivo = (
                    f"supportSpecimenId ausente para supportTestId='{support_test_id}'"
                )
                if support_test_id == "XXXX":
                    acao = (
                        "CodigoExame nao resolvido no banco (texame). Verifique se o exame pertence "
                        "a este destino e cadastre o CodTExame em CODTEXAME_MAP no .env."
                    )
                else:
                    acao = (
                        f"Codigo '{support_test_id}' nao existe no catalogo /tests do Bemsoft ou nao "
                        f"possui specimen. Ajuste BEMSOFT_TEST_MAP_PATH ou solicite o cadastro no Bemsoft."
                    )
                print(
                    f"[bemsoft] item {it.get('CodItemSol')} RECUSADO ('{it.get('DescExames')}'): {motivo}. "
                    f"Os demais itens da solicitacao {codsol} seguem normalmente."
                )
                rejeitados.append({"item": it, "motivo": motivo, "acao": acao})
                continue

        # Monta additionalInformations base
        additional_info = [
            {"key": "origem", "value": it.get("Origem") or "API"},
            {"key": "descricao", "value": it.get("DescExames") or ""},
            {"key": "observacao_codigo_exame", "value": it.get("ExameDescricao") or ""},
        ]

        # Adiciona dados do Google Sheets quando disponível
        if test_info:
            test_name = test_info.get("TEST_NAME")

            if test_name:
                additional_info.append({"key": "SUPPORT_TEST_NAME", "value": test_name})

            if descmat:
                additional_info.append({"key": "DESCMAT", "value": descmat})

            print(f"[sheets] Dados encontrados para '{support_test_id}': TEST_NAME='{test_name}', DESCMAT='{descmat}'")

        aceitos.append(it)
        tests.append({
            "externalId": item_ext,
            "collectionDate": d_col,
            "collectionTime": t_col,
            "supportTestId": support_test_id,
            "supportSpecimenId": specimen_id,
            "additionalInformations": additional_info,
            "condition": "",
            "preservative": "",
            "diuresisVolume": 0,
            "diuresisTime": 0,
        })

    if not tests:
        # Nada sobrou para enviar: devolve apenas os rejeitados.
        return None, rejeitados

    # Alinha a data do lote a data de coleta dos itens. Um teste com collectionDate
    # posterior ao batch.date e aceito com HTTP 201 mas nao gravado pelo WiseLab —
    # foi o que engoliu o acido mandelico (coleta de final de jornada, no dia seguinte).
    # Quando a coleta e no mesmo dia da solicitacao (caso comum) nada muda aqui, nem no
    # externalId, que continua no formato curto ja comprovado.
    sufixo_data = ""
    datas_coleta = {t["collectionDate"] for t in tests if t.get("collectionDate")}
    if len(datas_coleta) == 1:
        data_coleta = next(iter(datas_coleta))
        if data_coleta != bdate:
            sufixo_data = "-" + data_coleta[5:7] + data_coleta[8:10]   # -MMDD
            print(f"[bemsoft] lote da solicitação {codsol} alinhado à data de coleta "
                  f"{data_coleta} (solicitação é de {bdate}).")
            bdate = data_coleta
    elif len(datas_coleta) > 1:
        print(f"[bemsoft] AVISO: solicitação {codsol} com {len(datas_coleta)} datas de coleta "
              f"no mesmo lote ({sorted(datas_coleta)}); o WiseLab pode descartar as posteriores.")

    # externalId: o WiseLab grava estes campos. O formato longo
    # (sol-43335-cd27cc0df481) foi recusado com "nao foi possivel salvar os dados
    # recebidos no lote", entao o padrao volta a ser o formato curto original.
    # A variacao por conteudo fica apenas na Idempotency-Key (cabecalho HTTP, que o
    # WiseLab nao persiste como coluna). BEMSOFT_EXTID_SUFFIX=1 reativa o sufixo,
    # com tamanho ajustavel, caso o laboratorio confirme o limite do campo.
    fp = _itens_fingerprint(aceitos)
    if config.EXTID_SUFFIX:
        sufixo = "-" + fp[:config.EXTID_HASH_LEN]
    else:
        sufixo = ""
    sufixo = sufixo + sufixo_data
    batch_id = f"sol-{codsol}{sufixo}" if codsol is not None else f"sol-{_uuid()}"
    order_id = f"order-{codsol}{sufixo}" if codsol is not None else f"order-{_uuid()}"

    # Monta o order sem physician se não estiver disponível
    order_data = {
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
        "tests": tests,
    }

    # Adiciona physician apenas se houver dados completos
    if physician_data:
        order_data["physician"] = physician_data

    payload = {
        "batch": {
            "externalId": batch_id,
            "date": bdate,
            "time": btime,
            "order": order_data
        }
    }
    return payload, rejeitados

def send_to_bemsoft(event: Dict[str, Any], session: Optional[Session] = None, print_payload: bool = False) -> Dict[str, Any]:
    """Transforma e envia POST /requests (ou apenas gera no DRY_RUN)."""
    if config.DRY_RUN:
        payload_start = datetime.now()
        payload, rejeitados = build_payload(event, session=None)
        payload_end = datetime.now()
        payload_duration = (payload_end - payload_start).total_seconds()
        print(f"[{payload_end.strftime('%Y-%m-%d %H:%M:%S')}] [bemsoft] DRY_RUN ativo. Payload gerado em {payload_duration:.2f}s, não enviado.")
        if print_payload:
            import json
            print(f"\n== PAYLOAD ENVIADO ==\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n")
        return {"ok": True, "status": 200, "rejected": rejeitados,
                "data": {"dryRun": True, "payload": payload}}

    if not config.TOKEN:
        return {"ok": False, "status": 401, "rejected": [],
                "error": "BEMSOFT_TOKEN não configurado (Bearer)"}

    sess = session or _build_session()
    url = config.BASE_URL.rstrip("/") + config.REQS_ENDPOINT

    payload_start = datetime.now()
    payload, rejeitados = build_payload(event, session=sess)
    payload_end = datetime.now()
    payload_duration = (payload_end - payload_start).total_seconds()
    print(f"[{payload_end.strftime('%Y-%m-%d %H:%M:%S')}] [bemsoft] Payload construído em {payload_duration:.2f}s")

    if payload is None:
        # Todos os itens foram recusados na montagem: nao ha o que enviar.
        print(f"[bemsoft] nenhum item elegível após validação "
              f"({len(rejeitados)} recusado(s)); POST não realizado.")
        return {"ok": True, "status": 0, "rejected": rejeitados,
                "nothing_to_send": True, "data": None}

    aceitos = payload["batch"]["order"]["tests"]
    headers = {
        "Authorization": f"Bearer {config.TOKEN}",
        "Content-Type": "application/json",
        # Sempre sensivel ao conteudo, independente do formato do externalId: exames
        # acrescentados depois a uma solicitacao ja enviada produzem uma chave nova,
        # em vez de colidirem em 409 e serem descartados.
        "Idempotency-Key": _idemp_key(
            (event.get("solicitacao") or {}).get("codsolicitacao"),
            event.get("itens") or [],
        ),
    }

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

    # Log detalhado da resposta da API
    import json as json_log
    print(f"\n== RESPOSTA DA API BEMSOFT ==")
    print(f"Status Code: {status}")
    print(f"Headers: {dict(resp.headers)}")
    if isinstance(body, dict) or isinstance(body, list):
        print(f"Body (JSON):\n{json_log.dumps(body, ensure_ascii=False, indent=2)}")
    else:
        print(f"Body (Text): {body}")
    print(f"==========================\n")

    # 201: criado — mas só se o corpo não trouxer erro (o WiseLab devolve 201 com
    # {"error": ...} quando falha ao gravar o lote).
    if status == 201:
        erro_corpo = _erro_no_corpo(body)
        if erro_corpo:
            print(f"[bemsoft] ATENÇÃO: HTTP 201 com erro no corpo — o lote NÃO foi gravado: {erro_corpo}")
            return {"ok": False, "status": status, "error": erro_corpo, "rejected": rejeitados,
                    "body_error": True, "retryable": True}
        return {"ok": True, "status": status, "data": body, "rejected": rejeitados,
                "sent_count": len(aceitos)}

    # 409: Idempotência. Com a chave derivada do conjunto de itens, um 409 significa que
    # ESTE MESMO conjunto ja havia sido aceito antes — nada novo foi criado. Continua
    # contando como entregue (nao adianta reenviar), mas fica explicito no log.
    if status == 409:
        print(f"[bemsoft] 409 — conjunto idêntico já processado (chave={headers['Idempotency-Key']}); "
              f"NADA foi criado agora.")
        return {"ok": True, "status": status, "data": body, "idempotent": True,
                "rejected": rejeitados, "sent_count": 0}

    # 400: Erro de validação — reenviar igual não resolve.
    if status == 400:
        return {"ok": False, "status": status, "error": body, "validation_error": True,
                "rejected": rejeitados, "retryable": False}

    # 401: Token ausente ou inválido — reenviar igual não resolve.
    if status == 401:
        return {"ok": False, "status": status, "error": body, "auth_error": True,
                "rejected": rejeitados, "retryable": False}

    # Outros status codes 2xx — mesma validação de corpo
    if 200 <= status < 300:
        erro_corpo = _erro_no_corpo(body)
        if erro_corpo:
            print(f"[bemsoft] ATENÇÃO: HTTP {status} com erro no corpo — o lote NÃO foi gravado: {erro_corpo}")
            return {"ok": False, "status": status, "error": erro_corpo, "rejected": rejeitados,
                    "body_error": True, "retryable": True}
        return {"ok": True, "status": status, "data": body, "rejected": rejeitados,
                "sent_count": len(aceitos)}

    # 5xx e demais: transitório, vale reenviar.
    return {"ok": False, "status": status, "error": body, "rejected": rejeitados,
            "retryable": True}


# =========================================================================
# Fila de reenvio (espelha o comportamento do telemed_client)
# =========================================================================
# IMPORTANTE: a fila vive em FAILED_DIR/bemsoft_pending/, um diretório NOVO.
# Os JSON históricos na raiz de FAILED_DIR são dead-letter e NUNCA são
# reenviados automaticamente — evita duplicar o que já foi cadastrado à mão.

_CIRCUIT_RETRY_INTERVAL = 60

_down_since: Optional[float] = None
_last_attempt: Optional[float] = None


def _circuit_open() -> bool:
    """True enquanto o Bemsoft está inacessível e o intervalo não passou."""
    if _down_since is None:
        return False
    return (time.time() - (_last_attempt or _down_since)) < _CIRCUIT_RETRY_INTERVAL


def _on_connect_error(e: Exception) -> None:
    global _down_since, _last_attempt
    _last_attempt = time.time()
    if _down_since is None:
        _down_since = _last_attempt
        print(f"[bemsoft] serviço indisponível — próxima tentativa em {_CIRCUIT_RETRY_INTERVAL}s.")
        logger_txt.log_texto("envios", f"BEMSOFT INDISPONIVEL: {e}")


def _on_connect_ok() -> None:
    global _down_since, _last_attempt
    if _down_since is not None:
        print("[bemsoft] serviço disponível novamente.")
        logger_txt.log_texto("envios", "BEMSOFT DISPONIVEL NOVAMENTE")
    _down_since = None
    _last_attempt = None


def _get_pending_dir() -> str:
    path = os.path.join(config.FAILED_DIR, "bemsoft_pending")
    os.makedirs(path, exist_ok=True)
    return path


def _get_dead_dir() -> str:
    path = os.path.join(config.FAILED_DIR, "bemsoft_dead")
    os.makedirs(path, exist_ok=True)
    return path


def persist_pending(event: Dict[str, Any], reason: str = "", attempts: int = 0) -> Optional[str]:
    """Enfileira um evento para reenvio automático quando o Bemsoft voltar."""
    ts = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    cod = (event.get("solicitacao", {}) or {}).get("codsolicitacao", "unknown")
    path = os.path.join(_get_pending_dir(), f"{ts}_{cod}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"reason": reason, "attempts": attempts, "event": event},
                      f, ensure_ascii=False, indent=2, default=str)
        print(f"[bemsoft] evento enfileirado para reenvio: {path}")
        logger_txt.log_texto("envios", f"ENFILEIRADO sol={cod} motivo={reason} arquivo={os.path.basename(path)}")
        return path
    except Exception as e:
        print(f"[bemsoft] falha ao enfileirar evento da solicitação {cod}: {e}")
        return None


def _move_to_dead(fpath: str, motivo: str) -> None:
    try:
        dest = os.path.join(_get_dead_dir(), os.path.basename(fpath))
        os.replace(fpath, dest)
        print(f"[bemsoft] evento movido para dead-letter ({motivo}): {dest}")
        logger_txt.log_texto("envios", f"DEAD-LETTER {os.path.basename(fpath)} motivo={motivo}")
    except Exception as e:
        print(f"[bemsoft] falha ao mover {fpath} para dead-letter: {e}")


def retry_pending(session: Optional[Session] = None) -> int:
    """
    Reenvia eventos acumulados na fila do Bemsoft.
    Para no primeiro erro transitório (serviço ainda fora) e respeita o circuit breaker.
    Eventos que estouram MAX_RETRY_ATTEMPTS ou que falham por erro definitivo
    (400/401) vão para bemsoft_dead/ em vez de travar a fila.
    Retorna quantos foram entregues.
    """
    if config.DRY_RUN or _circuit_open():
        return 0

    pending_dir = _get_pending_dir()
    try:
        files = sorted(f for f in os.listdir(pending_dir) if f.endswith(".json"))
    except Exception:
        return 0
    if not files:
        return 0

    print(f"[bemsoft] {len(files)} evento(s) pendente(s) — tentando reenvio...")
    sent = 0

    for fname in files:
        fpath = os.path.join(pending_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            event = data["event"]
            attempts = int(data.get("attempts", 0)) + 1
        except Exception as e:
            print(f"[bemsoft] arquivo de fila ilegível {fname}: {e}")
            _move_to_dead(fpath, f"arquivo ilegivel: {e}")
            continue

        cod = (event.get("solicitacao", {}) or {}).get("codsolicitacao", "?")

        try:
            result = send_to_bemsoft(event, session=session, print_payload=False)
        except Exception as e:
            _on_connect_error(e)
            data["attempts"] = attempts
            data["reason"] = f"exceção no reenvio: {e}"
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            except Exception:
                pass
            if attempts >= config.MAX_RETRY_ATTEMPTS:
                _move_to_dead(fpath, f"{attempts} tentativas sem sucesso")
                continue
            break  # serviço ainda fora — não insiste neste ciclo

        rejeitados = result.get("rejected") or []
        if rejeitados:
            enviados_itens = [
                i for i in (event.get("itens") or [])
                if i not in [r.get("item") for r in rejeitados]
            ]
            logger_txt.log_rejeitados(event, rejeitados, enviados_itens, destino="Bemsoft (reenvio)")

        if result.get("idempotent"):
            # 409 durante um REENVIO e ambiguo: a chave pode ter ficado registrada na
            # tentativa que falhou, e entao nada seria criado agora. Nao apaga da fila
            # em silencio — manda para dead-letter para conferencia manual.
            _on_connect_ok()
            print(f"[bemsoft] reenvio da solicitação {cod} devolveu 409 — o WiseLab diz que "
                  f"ja processou esta chave, mas o envio anterior falhou. NAO confirmado como criado.")
            logger_txt.log_envio(event, "Bemsoft", event.get("itens") or [],
                                 "REENVIO 409 - NAO CONFIRMADO",
                                 "conferir manualmente no WiseLab")
            _move_to_dead(fpath, "409 no reenvio - exige conferencia manual")
            continue

        if result.get("ok"):
            _on_connect_ok()
            os.remove(fpath)
            sent += 1
            print(f"[bemsoft] reenvio OK: solicitação {cod} (tentativa {attempts})")
            logger_txt.log_envio(event, "Bemsoft", event.get("itens") or [],
                                 f"REENVIO OK status={result.get('status')}",
                                 f"tentativa {attempts}")
            continue

        # Falhou.
        if result.get("retryable") is False:
            logger_txt.log_envio(event, "Bemsoft", event.get("itens") or [],
                                 f"REENVIO FALHOU DEFINITIVO status={result.get('status')}",
                                 str(result.get("error"))[:300])
            _move_to_dead(fpath, f"erro definitivo HTTP {result.get('status')}")
            continue

        data["attempts"] = attempts
        data["reason"] = f"HTTP {result.get('status')}: {result.get('error')}"
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass

        if attempts >= config.MAX_RETRY_ATTEMPTS:
            _move_to_dead(fpath, f"{attempts} tentativas sem sucesso")
            continue

        # Distingue "servico fora" de "este evento falhou". Antes qualquer falha dava
        # break, e um unico evento que nunca vai passar bloqueava a fila inteira atras
        # dele (foi o que segurou o HTLV atras do acido mandelico).
        if result.get("status"):
            print(f"[bemsoft] reenvio da solicitação {cod} falhou (tentativa {attempts}); "
                  f"segue para o próximo da fila.")
            continue

        print(f"[bemsoft] reenvio da solicitação {cod} falhou (tentativa {attempts}); "
              f"serviço parece fora, pausa a fila neste ciclo.")
        break

    if sent:
        print(f"[bemsoft] {sent} evento(s) reenviado(s) com sucesso.")
    return sent
