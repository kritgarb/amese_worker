"""
Envia eventos do worker para o amese_telemed via POST /api/sync/exames.
Ativo apenas quando TELEMED_URL e TELEMED_TOKEN estão configurados.
"""

from typing import Any, Dict, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config


def _build_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=2,
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


def is_enabled() -> bool:
    return bool(config.TELEMED_URL and config.TELEMED_TOKEN)


def sync_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Envia um evento (solicitacao + paciente + itens) para o telemed.
    Retorna dict com 'ok', 'status' e detalhes.
    """
    if not is_enabled():
        return {"ok": False, "skipped": True, "reason": "TELEMED_URL/TELEMED_TOKEN não configurados"}

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
            created = body.get("created", []) if isinstance(body, dict) else []
            skipped = body.get("skipped", []) if isinstance(body, dict) else []
            print(f"[telemed] sincronizado: {len(created)} criado(s), {len(skipped)} já existente(s).")
            return {"ok": True, "status": status, "data": body}

        if status == 401:
            print(f"[telemed] erro de autenticação — verifique TELEMED_TOKEN.")
            return {"ok": False, "status": status, "error": body}

        print(f"[telemed] erro HTTP {status}: {body}")
        return {"ok": False, "status": status, "error": body}

    except requests.exceptions.Timeout:
        print(f"[telemed] timeout ao chamar {url}")
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        print(f"[telemed] exceção: {e}")
        return {"ok": False, "error": str(e)}
