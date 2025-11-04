import os
import sys
import time
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime, time as dt_time

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import config
import database
import bemsoft_api


PENDING_SOLICITACOES: Dict[Any, float] = {}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dt_time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, Decimal):
        return float(value)
    return value


def _json_default(value: Any) -> Any:
    normalized = _normalize_value(value)
    if normalized is value:
        return str(value)
    return normalized


def persist_failed(event: Dict[str, Any], reason: str = ""):
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    key = event.get("solicitacao", {}).get("codsolicitacao", "unknown")
    path = os.path.join(config.FAILED_DIR, f"{ts}_{key}.json")
    data = {"reason": reason, "event": event}
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default))
    print(f"[fail] salvo para retry manual: {path}")


def row_to_item(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "CodItemSol": _normalize_value(r["CodItemSol"]),
        "DataEntrada": _normalize_value(r["DataEntrada"]),
        "DescExames": _normalize_value(r["DescExames"]),
        "CodigoExame": _normalize_value(r["CodConvExames"]),
        "NomeTerceirizado": _normalize_value(r["NomeTerceirizado"]),
        "Valor": _normalize_value(r["Valor"]),
        "VlTerceirizado": _normalize_value(r["VlTerceirizado"]),
        "SituacaoResultado": _normalize_value(r["SituacaoResultado"]),
        "Origem": _normalize_value(r["Origem"]),
        "ExameDescricao": _normalize_value(r.get("ExameDescricao")),
    }


def build_group_event(head_row: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
    solicitacao = {
        "codsolicitacao": _normalize_value(head_row["CodSolicitacao"]),
        "codpaciente": _normalize_value(head_row["codpaciente"]),
        "CodConvenio": _normalize_value(head_row["CodConvenio"]),
        "dtaentrada": _normalize_value(head_row["Sol_dtaentrada"]),
        "Hora": _normalize_value(head_row["Hora"]),
        "Valortotal": _normalize_value(head_row["Valortotal"]),
        "TipoPgto": _normalize_value(head_row["TipoPgto"]),
        "Obs_Sol": _normalize_value(head_row["Obs_Sol"]),
    }
    paciente = {
        "nome": _normalize_value(head_row["PacienteNome"]),
        "cpf": _normalize_value(head_row["PacienteCPF"]),
        "datanasc": _normalize_value(head_row["PacienteNascimento"]),
        "fone": _normalize_value(head_row["PacienteFone"]),
        "email": _normalize_value(head_row["PacienteEmail"]),
        "cidade": _normalize_value(head_row["PacienteCidade"]),
        "uf": _normalize_value(head_row["PacienteUF"]),
        "sexo": _normalize_value(head_row.get("PacienteSexo")),
        "codpaciente": _normalize_value(head_row.get("codpaciente")),
    }
    return {"solicitacao": solicitacao, "paciente": paciente, "itens": items}


def poll_once(sess_http: Optional[bemsoft_api.Session]) -> int:
    """Lê last_id, busca novos itens, debounce, agrupa por solicitação e envia 1 payload por grupo."""
    with database.ENGINE.begin() as conn:
        last = conn.execute(database.SQL_GET_LAST).scalar() or 0
        rows = database.fetch_items(conn, last, config.TERCEIROS)
        if not rows:
            return last

        # Agrupa por solicitação
        groups: Dict[Any, Dict[str, Any]] = {}
        for r in rows:
            k = r["CodSolicitacao"]
            if k not in groups:
                groups[k] = {"head": r, "items": []}
            groups[k]["items"].append(row_to_item(r))

        now_ts = time.time()
        ready_groups: List[Tuple[Any, Dict[str, Any]]] = []
        pending_count = 0

        if config.DEBOUNCE_SECONDS > 0:
            stale = [k for k in list(PENDING_SOLICITACOES.keys()) if k not in groups]
            for key in stale:
                PENDING_SOLICITACOES.pop(key, None)

        for cod, g in groups.items():
            if config.DEBOUNCE_SECONDS > 0:
                first_seen = PENDING_SOLICITACOES.setdefault(cod, now_ts)
                wait_remaining = config.DEBOUNCE_SECONDS - (now_ts - first_seen)
                if wait_remaining > 0:
                    pending_count += 1
                    if first_seen == now_ts or wait_remaining <= config.POLL_SECONDS:
                        seconds_left = int(wait_remaining)
                        if seconds_left < 1:
                            seconds_left = 1
                        print(
                            f"[debounce] solicitação {cod} aguardando {seconds_left}s antes do envio."
                        )
                    continue
            ready_groups.append((cod, g))

        if not ready_groups:
            if pending_count:
                print(
                    f"[debounce] aguardando {pending_count} solicitação(ões) na fila"
                    f" (janela {config.DEBOUNCE_SECONDS}s)."
                )
            return last

        new_last = last
        for cod, g in ready_groups:
            event = build_group_event(g["head"], g["items"])
            print(
                f"\n== SOLICITAÇÃO {cod} | itens={len(g['items'])} ==\n"
                f"{json.dumps(event, ensure_ascii=False, indent=2, default=_json_default)}\n"
            )
            try:
                result = bemsoft_api.send_to_bemsoft(event, session=sess_http)
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
            PENDING_SOLICITACOES.pop(cod, None)

        conn.execute(database.SQL_SET_LAST, {"last": new_last})
        return new_last


def main():
    print("Monitor ItemSol -> Bemsoft iniciado.")
    filtro = ", ".join(config.TERCEIROS) if config.TERCEIROS else "<sem filtro>"
    print(
        f"Filtro TERCEIROS='{filtro}' | Poll={config.POLL_SECONDS}s | "
        f"Debounce={config.DEBOUNCE_SECONDS}s | DRY_RUN={config.DRY_RUN}"
    )
    if not config.DRY_RUN and not config.TOKEN:
        print(
            "[warn] BEMSOFT_TOKEN ausente. Ative DRY_RUN=1 ou configure o token."
        )
    # Bootstrap estado
    database.bootstrap_state()
    # Sessão HTTP única (reuso/keep-alive)
    sess_http = bemsoft_api._build_session() if not config.DRY_RUN else None

    try:
        while True:
            try:
                poll_once(sess_http)
            except Exception as e:
                print(f"[ERRO] ciclo falhou: {e}")
            time.sleep(config.POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nEncerrado pelo usuário.")


if __name__ == "__main__":
    main()
