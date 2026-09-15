"""
Envia eventos do worker para o amese_telemed via POST /api/sync/exames.
Ativo apenas quando TELEMED_URL e TELEMED_TOKEN estão configurados.
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

# Intervalo mínimo entre tentativas quando o telemed está fora (segundos)
_CIRCUIT_RETRY_INTERVAL = 60

_down_since: Optional[float] = None   # timestamp da primeira falha de conexão
_last_attempt: Optional[float] = None  # timestamp da última tentativa quando o circuito está aberto


def _circuit_open() -> bool:
    """Retorna True enquanto o telemed está inacessível e o intervalo não passou."""
    if _down_since is None:
        return False
    elapsed_since_last = time.time() - (_last_attempt or _down_since)
    return elapsed_since_last < _CIRCUIT_RETRY_INTERVAL


def _on_connect_error(e: Exception) -> None:
    global _down_since, _last_attempt
    _last_attempt = time.time()
    if _down_since is None:
        _down_since = _last_attempt
        print(f"[telemed] serviço indisponível — próxima tentativa em {_CIRCUIT_RETRY_INTERVAL}s.")


def _on_connect_ok() -> None:
    global _down_since, _last_attempt
    if _down_since is not None:
        print("[telemed] serviço disponível novamente.")
    _down_since = None
    _last_attempt = None


def _build_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=2,
        connect=0,          # falha rápida em erro de conexão — circuit breaker cuida do backoff
        backoff_factor=0.3,
        status_forcelist=[502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = _build_session()
    return _SESSION


def _get_pending_dir() -> str:
    path = os.path.join(config.FAILED_DIR, "telemed_pending")
    os.makedirs(path, exist_ok=True)
    return path


def is_enabled() -> bool:
    return bool(config.TELEMED_URL and config.TELEMED_TOKEN)


def get_filtros() -> list:
    """
    Busca a lista de NomeTerceirizado configurados para o Telemed.
    Retorna lista vazia em caso de erro (worker não interrompe o ciclo).
    """
    if not is_enabled() or _circuit_open():
        return []

    url = config.TELEMED_URL + "/api/sync/filtros"
    headers = {"Authorization": f"Bearer {config.TELEMED_TOKEN}"}

    try:
        resp = _get_session().get(url, headers=headers, timeout=config.TELEMED_TIMEOUT)
        if resp.status_code == 200:
            _on_connect_ok()
            return resp.json()
        print(f"[telemed] erro ao buscar filtros (HTTP {resp.status_code})")
        return []
    except Exception as e:
        _on_connect_error(e)
        return []


def sync_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Envia um evento (solicitacao + paciente + itens) para o telemed.
    Retorna dict com 'ok', 'status' e detalhes.
    """
    if not is_enabled():
        return {"ok": False, "skipped": True, "reason": "TELEMED_URL/TELEMED_TOKEN não configurados"}

    if _circuit_open():
        return {"ok": False, "error": "telemed indisponível (circuit open)", "circuit_open": True}

    url = config.TELEMED_URL + "/api/sync/exames"
    headers = {
        "Authorization": f"Bearer {config.TELEMED_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        resp = _get_session().post(url, json=event, headers=headers, timeout=config.TELEMED_TIMEOUT)
        status = resp.status_code
        try:
            body = resp.json()
        except Exception:
            body = resp.text

        if status in (200, 201):
            _on_connect_ok()
            created = body.get("created", []) if isinstance(body, dict) else []
            skipped = body.get("skipped", []) if isinstance(body, dict) else []
            print(f"[telemed] sincronizado: {len(created)} criado(s), {len(skipped)} já existente(s).")
            return {"ok": True, "status": status, "data": body}

        if status == 401:
            print(f"[telemed] erro de autenticação — verifique TELEMED_TOKEN.")
            return {"ok": False, "status": status, "error": body, "auth_error": True}

        print(f"[telemed] erro HTTP {status}: {body}")
        return {"ok": False, "status": status, "error": body}

    except requests.exceptions.Timeout:
        _on_connect_error(Exception("timeout"))
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        _on_connect_error(e)
        return {"ok": False, "error": str(e)}


def persist_pending(event: Dict[str, Any], reason: str = "") -> None:
    """Salva evento em fila local para reenvio quando o telemed voltar."""
    ts = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    cod = event.get("solicitacao", {}).get("codsolicitacao", "unknown")
    path = os.path.join(_get_pending_dir(), f"{ts}_{cod}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"reason": reason, "event": event}, f, ensure_ascii=False, indent=2)
    print(f"[telemed] evento enfileirado para reenvio: {path}")


def retry_pending() -> int:
    """
    Tenta reenviar eventos pendentes acumulados enquanto o telemed estava fora.
    Só roda se o circuit breaker permitir uma nova tentativa.
    Para no primeiro erro (telemed ainda indisponível).
    Retorna o número de eventos reenviados com sucesso.
    """
    if not is_enabled() or _circuit_open():
        return 0

    pending_dir = _get_pending_dir()
    files = sorted(f for f in os.listdir(pending_dir) if f.endswith(".json"))
    if not files:
        return 0

    print(f"[telemed] {len(files)} evento(s) pendente(s) — tentando reenvio...")
    sent = 0

    for fname in files:
        fpath = os.path.join(pending_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            event = data["event"]
            result = sync_event(event)
            if result.get("ok"):
                os.remove(fpath)
                sent += 1
                cod = event.get("solicitacao", {}).get("codsolicitacao", "?")
                print(f"[telemed] reenvio OK: solicitação {cod}")
            else:
                break  # telemed ainda indisponível — para de tentar neste ciclo
        except Exception as e:
            print(f"[telemed] erro ao reenviar {fname}: {e}")
            break

    if sent:
        print(f"[telemed] {sent} evento(s) reenviado(s) com sucesso.")
    return sent
