"""
Log em .txt legível para operação/auditoria.

Complementa os JSON de failed_events (que servem para reprocessamento) com um
relatório humano do que foi enviado, do que foi recusado e por quê.

Arquivos gerados em config.LOG_DIR:
  - rejeitados_YYYY-MM-DD.txt  -> itens que o Bemsoft não aceitou (sem specimen/código)
  - envios_YYYY-MM-DD.txt      -> resumo de cada despacho (destino, itens, resultado)
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import config

_SEP = "=" * 100


def _path(prefix: str) -> str:
    os.makedirs(config.LOG_DIR, exist_ok=True)
    return os.path.join(config.LOG_DIR, f"{prefix}_{datetime.now().strftime('%Y-%m-%d')}.txt")


def _write(prefix: str, texto: str) -> Optional[str]:
    path = _path(prefix)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(texto)
        return path
    except Exception as e:
        print(f"[log] falha ao gravar {path}: {e}")
        return None


def _cab(event: Dict[str, Any]) -> List[str]:
    sol = event.get("solicitacao", {}) or {}
    pac = event.get("paciente", {}) or {}
    return [
        f"Solicitacao : {sol.get('codsolicitacao')}",
        f"Paciente    : {pac.get('nome')}  (codpaciente={pac.get('codpaciente')}, CPF={pac.get('cpf')})",
        f"Convenio    : {sol.get('CodConvenio')}",
        f"Entrada     : {sol.get('dtaentrada')} {sol.get('Hora')}",
    ]


def log_rejeitados(event: Dict[str, Any], rejeitados: List[Dict[str, Any]],
                   enviados: List[Dict[str, Any]], destino: str = "Bemsoft") -> Optional[str]:
    """
    Registra, em texto corrido, os itens que foram recusados na montagem do payload
    e quais itens da mesma solicitação seguiram viagem mesmo assim.
    """
    if not rejeitados:
        return None

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linhas = [
        "",
        _SEP,
        f"[{ts}] ITENS REJEITADOS NA MONTAGEM DO PAYLOAD  ->  destino: {destino}",
        _SEP,
    ]
    linhas += _cab(event)
    linhas.append("")
    linhas.append(f"REJEITADOS ({len(rejeitados)}) - NAO foram enviados, exigem acao manual:")
    for r in rejeitados:
        it = r.get("item", {}) or {}
        linhas.append(f"  - CodItemSol      : {it.get('CodItemSol')}")
        linhas.append(f"    Exame           : {it.get('DescExames')}")
        linhas.append(f"    CodigoExame     : {it.get('CodigoExame')}")
        linhas.append(f"    Terceirizado    : {it.get('NomeTerceirizado')}")
        linhas.append(f"    Valor           : {it.get('Valor')} / terceiro {it.get('VlTerceirizado')}")
        linhas.append(f"    MOTIVO          : {r.get('motivo')}")
        linhas.append(f"    COMO RESOLVER   : {r.get('acao')}")
        linhas.append("")

    if enviados:
        linhas.append(f"ENVIADOS NORMALMENTE ({len(enviados)}) - o restante da solicitacao seguiu:")
        for it in enviados:
            linhas.append(f"  - {it.get('CodItemSol')} | {it.get('CodigoExame')} | {it.get('DescExames')}")
    else:
        linhas.append("ENVIADOS NORMALMENTE (0) - nenhum item restou, nada foi enviado ao destino.")
    linhas.append("")

    return _write("rejeitados", "\n".join(linhas))


def log_envio(event: Dict[str, Any], destino: str, itens: List[Dict[str, Any]],
              resultado: str, detalhe: str = "") -> Optional[str]:
    """Uma linha-resumo por despacho, para reconstruir o que saiu do worker."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sol = event.get("solicitacao", {}) or {}
    pac = event.get("paciente", {}) or {}
    ids = ",".join(str(i.get("CodItemSol")) for i in itens)
    linha = (
        f"[{ts}] {destino:<8} sol={sol.get('codsolicitacao')} "
        f"pac={str(pac.get('nome') or '').strip()[:40]!r} "
        f"itens={len(itens)} [{ids}] -> {resultado}"
    )
    if detalhe:
        linha += f" | {detalhe}"
    return _write("envios", linha + "\n")


def log_texto(prefix: str, texto: str) -> Optional[str]:
    """Escape hatch para mensagens avulsas (ex.: fila de reenvio)."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return _write(prefix, f"[{ts}] {texto}\n")
