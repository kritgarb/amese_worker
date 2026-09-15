import os
import sys
import time
import json
import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime, time as dt_time
import dotenv
from dotenv import load_dotenv
from sqlalchemy import text

# Detecta se está rodando como executável PyInstaller
if getattr(sys, 'frozen', False):
    # Rodando como executável - módulos já estão no path do PyInstaller
    pass
else:
    # Rodando em desenvolvimento - adiciona src/ ao path
    ROOT_DIR = Path(__file__).resolve().parent
    SRC_DIR = ROOT_DIR / "src"
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

import config
import database
import bemsoft_api
import telemed_client
import logger_txt


_DESC_TO_CODIGO_CACHE: Dict[str, Optional[str]] = {}


def _normalize_desc(desc: str) -> str:
    """Normaliza descrição de exame para matching."""
    return desc.strip().upper().replace("  ", " ")


def _fallback_codigo_by_desc(desc_exame: str, cod_texame: Optional[int]) -> Optional[str]:
    """
    Busca CodigoExame pela descrição quando o LEFT JOIN falha (integridade referencial quebrada).
    Primeiro tenta o mapping manual CODTEXAME_MAP, depois busca por descrição.
    """
    # 1. Tenta mapping manual CodTExame -> CodigoExame
    if cod_texame and cod_texame in config.CODTEXAME_MAP:
        codigo = config.CODTEXAME_MAP[cod_texame]
        print(f"[mapping] CodTExame={cod_texame} -> '{codigo}' (CODTEXAME_MAP)")
        return codigo

    if not desc_exame:
        return None

    desc_norm = _normalize_desc(desc_exame)

    # 2. Verifica cache de busca por descrição
    if desc_norm in _DESC_TO_CODIGO_CACHE:
        cached = _DESC_TO_CODIGO_CACHE[desc_norm]
        if cached:
            print(f"[fallback] Usando cache: '{desc_exame}' -> '{cached}' (CodTExame={cod_texame} não encontrado)")
        return cached

    # 3. Busca no banco pela descrição
    try:
        with database.ENGINE.begin() as conn:
            result = conn.execute(
                text("SELECT TOP 1 CodigoExame FROM dbo.texame WHERE UPPER(LTRIM(RTRIM(descricao))) = :desc"),
                {"desc": desc_norm}
            ).fetchone()

            if result and result[0]:
                codigo = result[0]
                _DESC_TO_CODIGO_CACHE[desc_norm] = codigo
                print(f"[fallback] '{desc_exame}' -> '{codigo}' (CodTExame={cod_texame} não existe, buscado por descrição)")
                return codigo
            else:
                _DESC_TO_CODIGO_CACHE[desc_norm] = None
                print(f"[fallback] Aviso: Descrição '{desc_exame}' não encontrada na tabela texame (CodTExame={cod_texame})")
                return None

    except Exception as e:
        print(f"[fallback] Erro ao buscar código por descrição '{desc_exame}': {e}")
        return None


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
    ts = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    key = event.get("solicitacao", {}).get("codsolicitacao", "unknown")
    path = os.path.join(config.FAILED_DIR, f"{ts}_{key}.json")
    data = {"reason": reason, "event": event}
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default))
    print(f"[fail] salvo para retry manual: {path}")


def row_to_item(r: Dict[str, Any]) -> Dict[str, Any]:
    codigo_exame = r.get("CodigoExame")

    # Se CodigoExame for NULL ou vazio, tenta buscar pela descrição
    if not codigo_exame or str(codigo_exame).strip() == "":
        desc_exame = r.get("DescExames", "")
        codigo_exame = _fallback_codigo_by_desc(desc_exame, r.get("CodTExame"))
        if not codigo_exame:
            codigo_exame = "XXXX"

    return {
        "CodItemSol": _normalize_value(r["CodItemSol"]),
        "DataEntrada": _normalize_value(r["DataEntrada"]),
        "DescExames": _normalize_value(r["DescExames"]),
        "CodigoExame": _normalize_value(codigo_exame),
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
        "Medico": _normalize_value(head_row.get("Medico")),
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


def _group_fingerprint(head_row: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
    """
    Assinatura do conteudo da solicitacao (cabecalho + itens).

    Qualquer edicao feita antes do envio — incluir, alterar ou remover um exame,
    ou corrigir dados do paciente — muda esta assinatura e reinicia a janela de
    debounce, de modo que o payload enviado seja sempre a versao final.
    """
    cabecalho = [
        head_row.get("codpaciente"), head_row.get("CodConvenio"),
        head_row.get("Sol_dtaentrada"), head_row.get("Hora"),
        head_row.get("Valortotal"), head_row.get("TipoPgto"), head_row.get("Obs_Sol"),
        head_row.get("Medico"), head_row.get("PacienteNome"), head_row.get("PacienteCPF"),
        head_row.get("PacienteNascimento"), head_row.get("PacienteSexo"),
    ]
    corpo = sorted(
        (
            i.get("CodItemSol"), i.get("CodigoExame"), i.get("DescExames"),
            i.get("NomeTerceirizado"), i.get("Valor"), i.get("VlTerceirizado"),
            i.get("DataEntrada"), i.get("SituacaoResultado"), i.get("Origem"),
        )
        for i in items
    )
    bruto = repr([_normalize_value(v) for v in cabecalho]) + repr(corpo)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def poll_once(sess_http: Optional[bemsoft_api.Session]) -> int:
    """Lê last_id, busca novos itens, debounce, agrupa por solicitação e envia 1 payload por grupo."""
    poll_start = datetime.now()

    with database.ENGINE.begin() as conn:
        query_start = datetime.now()
        last = conn.execute(database.SQL_GET_LAST).scalar() or 0
        bemsoft_api.retry_pending(session=sess_http)
        telemed_client.retry_pending()
        # A lista do amese_telemed manda, mas TELEMED_TERCEIROS do .env COMPLEMENTA
        # (antes era apenas fallback: com a API no ar, o .env era ignorado).
        telemed_filtros = list(dict.fromkeys(
            (telemed_client.get_filtros() or []) + config.TELEMED_TERCEIROS
        ))
        all_terceiros = list(dict.fromkeys(config.TERCEIROS + telemed_filtros))
        rows = database.fetch_items(conn, last, all_terceiros)
        query_end = datetime.now()
        query_duration = (query_end - query_start).total_seconds()

        if not rows:
            return last

        print(f"[{query_end.strftime('%Y-%m-%d %H:%M:%S')}] Encontrados {len(rows)} itens em {query_duration:.2f}s")

        # Agrupa por solicitação
        groups: Dict[Any, Dict[str, Any]] = {}
        for r in rows:
            k = r["CodSolicitacao"]
            if k not in groups:
                groups[k] = {"head": r, "items": []}
            groups[k]["items"].append(row_to_item(r))

        agora = datetime.now()
        ready_groups: List[Tuple[Any, Dict[str, Any]]] = []
        pending_count = 0

        if config.DEBOUNCE_SECONDS > 0:
            pendentes = database.pending_load(conn)

            # Solicitações que sumiram da consulta (todos os itens excluídos) saem do controle.
            for key in [k for k in pendentes if k not in groups]:
                database.pending_delete(conn, key)
                pendentes.pop(key, None)

            for cod, g in groups.items():
                assinatura = _group_fingerprint(g["head"], g["items"])
                estado = pendentes.get(cod)

                if estado is None:
                    # Primeira vez que vemos esta solicitação: abre a janela de edição.
                    database.pending_upsert(conn, cod, assinatura, agora, agora)
                    first_seen, last_change, editada = agora, agora, False
                elif estado["hash"] != assinatura:
                    # Conteúdo mudou (exame incluído, editado ou removido) -> reinicia a janela.
                    first_seen = estado["first_seen"]
                    database.pending_upsert(conn, cod, assinatura, first_seen, agora)
                    last_change, editada = agora, True
                else:
                    first_seen, last_change, editada = estado["first_seen"], estado["last_change"], False

                desde_mudanca = (agora - last_change).total_seconds()
                desde_inicio = (agora - first_seen).total_seconds()
                wait_remaining = config.DEBOUNCE_SECONDS - desde_mudanca

                # Teto absoluto: edição contínua não segura a solicitação para sempre.
                estourou_teto = (
                    config.MAX_DEBOUNCE_SECONDS > 0 and desde_inicio >= config.MAX_DEBOUNCE_SECONDS
                )

                if wait_remaining > 0 and not estourou_teto:
                    pending_count += 1
                    if editada:
                        print(
                            f"[debounce] solicitação {cod} EDITADA - janela reiniciada, "
                            f"novo envio em {int(wait_remaining)}s."
                        )
                    elif estado is None or wait_remaining <= config.POLL_SECONDS:
                        print(
                            f"[debounce] solicitação {cod} aguardando "
                            f"{max(1, int(wait_remaining))}s antes do envio."
                        )
                    continue

                if estourou_teto and wait_remaining > 0:
                    print(
                        f"[debounce] solicitação {cod} atingiu o teto de "
                        f"{config.MAX_DEBOUNCE_SECONDS}s de edição - enviando a versão atual."
                    )
                ready_groups.append((cod, g))
        else:
            ready_groups = list(groups.items())

        if not ready_groups:
            if pending_count:
                print(
                    f"[debounce] aguardando {pending_count} solicitação(ões) na fila"
                    f" (janela {config.DEBOUNCE_SECONDS}s)."
                )
            return last

        bemsoft_set = set(config.TERCEIROS)
        telemed_set  = set(telemed_filtros)

        new_last = last
        concluidos = set()   # solicitações cujos itens já têm destino resolvido neste ciclo

        for cod, g in ready_groups:
            send_start = datetime.now()

            # ---------------------------------------------------------------
            # Um payload POR DESTINO, contendo somente os itens daquele destino.
            # Antes o evento inteiro ia para os dois lados, e um exame de imagem
            # (ex.: ECG) entrava no payload do laboratório sem código, derrubando
            # a solicitação inteira.
            # ---------------------------------------------------------------
            itens_bemsoft = [i for i in g["items"] if i.get("NomeTerceirizado") in bemsoft_set]
            itens_telemed = [i for i in g["items"] if i.get("NomeTerceirizado") in telemed_set]

            destinos = []
            if itens_bemsoft:
                destinos.append(f"Bemsoft({len(itens_bemsoft)})")
            if itens_telemed and telemed_client.is_enabled():
                destinos.append(f"Telemed({len(itens_telemed)})")
            lista_destinos = ", ".join(destinos) or "nenhum destino"
            total_itens = len(g["items"])
            print(
                f"[{send_start.strftime('%Y-%m-%d %H:%M:%S')}] Enviando solicitação {cod} com "
                f"{total_itens} item(ns) -> {lista_destinos}..."
            )

            itens_ok: List[Any] = []   # CodItemSol que não devem mais ser reprocessados

            # ----------------------------- Bemsoft -----------------------------
            if itens_bemsoft:
                event_b = build_group_event(g["head"], itens_bemsoft)
                try:
                    result = bemsoft_api.send_to_bemsoft(event_b, session=sess_http, print_payload=True)
                    send_end = datetime.now()
                    send_duration = (send_end - send_start).total_seconds()

                    ok = result.get("ok")
                    status = result.get("status")
                    rejeitados = result.get("rejected") or []
                    ids_rejeitados = {(r.get("item") or {}).get("CodItemSol") for r in rejeitados}
                    itens_aceitos = [i for i in itens_bemsoft if i["CodItemSol"] not in ids_rejeitados]

                    # Detalhamento em .txt dos itens recusados e do que seguiu mesmo assim
                    if rejeitados:
                        caminho = logger_txt.log_rejeitados(
                            event_b, rejeitados, itens_aceitos, destino="Bemsoft"
                        )
                        print(
                            f"[bemsoft] {len(rejeitados)} item(ns) recusado(s) e "
                            f"{len(itens_aceitos)} enviado(s). Detalhes: {caminho}"
                        )

                    if ok:
                        if result.get("nothing_to_send"):
                            print(
                                f"[{send_end.strftime('%Y-%m-%d %H:%M:%S')}] [bemsoft] nada enviado: "
                                f"todos os {len(rejeitados)} item(ns) foram recusados."
                            )
                        elif result.get("idempotent"):
                            print(
                                f"[{send_end.strftime('%Y-%m-%d %H:%M:%S')}] [bemsoft] 409 - conjunto já "
                                f"processado antes; nada criado agora (tempo: {send_duration:.2f}s)."
                            )
                        else:
                            enviados_n = result.get("sent_count", len(itens_aceitos))
                            print(
                                f"[{send_end.strftime('%Y-%m-%d %H:%M:%S')}] [bemsoft] entregue com sucesso "
                                f"({enviados_n} item(ns), status={status}, tempo: {send_duration:.2f}s)."
                            )
                        logger_txt.log_envio(
                            event_b, "Bemsoft", itens_aceitos,
                            f"OK status={status}",
                            f"{len(rejeitados)} recusado(s)" if rejeitados else "",
                        )
                        # Aceitos e recusados são terminais: os recusados já estão no .txt e
                        # reenviar sem corrigir o cadastro não mudaria o resultado.
                        itens_ok += [i["CodItemSol"] for i in itens_bemsoft]
                    else:
                        erro = result.get("error")
                        print(
                            f"[{send_end.strftime('%Y-%m-%d %H:%M:%S')}] [bemsoft] erro (status={status}, "
                            f"tempo: {send_duration:.2f}s): {erro}"
                        )
                        logger_txt.log_envio(
                            event_b, "Bemsoft", itens_aceitos,
                            f"ERRO status={status}", str(erro)[:300]
                        )
                        if result.get("retryable") is False:
                            # 400/401: reenviar igual não resolve -> dead-letter, exige ação humana.
                            persist_failed(event_b, reason=f"HTTP {status}: {erro}")
                        else:
                            bemsoft_api.persist_pending(event_b, reason=f"HTTP {status}: {erro}")
                        itens_ok += [i["CodItemSol"] for i in itens_bemsoft]
                except Exception as e:
                    send_end = datetime.now()
                    send_duration = (send_end - send_start).total_seconds()
                    print(
                        f"[{send_end.strftime('%Y-%m-%d %H:%M:%S')}] [bemsoft] exceção ao enviar "
                        f"(tempo: {send_duration:.2f}s): {e}"
                    )
                    logger_txt.log_envio(event_b, "Bemsoft", itens_bemsoft, "EXCECAO", str(e)[:300])
                    bemsoft_api.persist_pending(event_b, reason=str(e))
                    itens_ok += [i["CodItemSol"] for i in itens_bemsoft]

            # ----------------------------- Telemed -----------------------------
            if itens_telemed and telemed_client.is_enabled():
                event_t = build_group_event(g["head"], itens_telemed)
                t_result = telemed_client.sync_event(event_t)
                if t_result.get("ok"):
                    logger_txt.log_envio(
                        event_t, "Telemed", itens_telemed, f"OK status={t_result.get('status')}"
                    )
                else:
                    logger_txt.log_envio(
                        event_t, "Telemed", itens_telemed, "ERRO", str(t_result.get("error"))[:300]
                    )
                    if not t_result.get("auth_error"):
                        telemed_client.persist_pending(event_t, reason=str(t_result.get("error", "")))
                itens_ok += [i["CodItemSol"] for i in itens_telemed]

            # Itens sem destino configurado (ex.: MAIS LAUDOS) normalmente nem voltam
            # na query; se voltarem, ficam registrados para não travarem o watermark.
            sem_destino = [
                i["CodItemSol"] for i in g["items"]
                if i.get("NomeTerceirizado") not in bemsoft_set
                and i.get("NomeTerceirizado") not in telemed_set
            ]
            if sem_destino:
                database.mark_items_sent(conn, sem_destino, cod, "nenhum", "sem destino")

            if itens_ok:
                database.mark_items_sent(conn, itens_ok, cod, lista_destinos, "despachado")

            concluidos.add(cod)
            group_max = max(i["CodItemSol"] for i in g["items"])
            new_last = max(new_last, group_max)
            if config.DEBOUNCE_SECONDS > 0:
                database.pending_delete(conn, cod)

        # ---------------------------------------------------------------------
        # Watermark (last_id): CodItemSol é uma sequência GLOBAL e os itens de
        # solicitações diferentes ficam intercalados. Avançar até o maior ID
        # enviado pulava permanentemente os itens de grupos ainda em debounce.
        # Agora o last_id nunca ultrapassa o menor item pendente, e a tabela
        # _MonitorSent garante que nada já despachado volte a ser enviado.
        # ---------------------------------------------------------------------
        pendentes_min = [
            min(i["CodItemSol"] for i in gg["items"])
            for c, gg in groups.items() if c not in concluidos
        ]
        if pendentes_min:
            limite = min(pendentes_min) - 1
            if limite < new_last:
                print(
                    f"[watermark] last_id retido em {limite}: "
                    f"{len(pendentes_min)} solicitação(ões) em debounce com itens abaixo de {new_last}."
                )
            new_last = max(last, min(new_last, limite))

        update_start = datetime.now()
        conn.execute(database.SQL_SET_LAST, {"last": new_last})
        update_end = datetime.now()
        print(f"[{update_end.strftime('%Y-%m-%d %H:%M:%S')}] Estado atualizado para last_id={new_last}")

        poll_end = datetime.now()
        poll_duration = (poll_end - poll_start).total_seconds()
        print(f"[{poll_end.strftime('%Y-%m-%d %H:%M:%S')}] Ciclo concluído em {poll_duration:.2f}s\n")

        return new_last

def main():
    print("Monitor ItemSol -> Bemsoft iniciado.")
    filtro = ", ".join(config.TERCEIROS) if config.TERCEIROS else "<sem filtro>"
    print(
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
