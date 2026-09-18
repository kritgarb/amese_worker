"""
Recoloca na fila de reenvio do Bemsoft solicitacoes que o worker deu por entregues
mas que o WiseLab nao gravou (resposta HTTP 201 com {"error": ...} no corpo).

Uso:
    python reenfileirar_bemsoft.py                      # simula, nao grava nada
    python reenfileirar_bemsoft.py --data 2026-09-16    # simula a partir de uma data
    python reenfileirar_bemsoft.py --sol 43313,43314    # simula solicitacoes especificas
    python reenfileirar_bemsoft.py --item 173976        # apenas itens especificos
    python reenfileirar_bemsoft.py --data 2026-09-16 --confirmar   # grava na fila

Os eventos sao escritos em completo/failed_events/bemsoft_pending/ e o proprio
worker reenvia no ciclo seguinte. NAO faz POST direto.

ATENCAO: so use depois de confirmar com o laboratorio que os lotes realmente nao
entraram. Reenfileirar algo que foi gravado gera exame duplicado.
"""
import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import config
import database
import bemsoft_api
from main import row_to_item, build_group_event, _split_por_data_coleta
from sqlalchemy import text

SQL_ITENS = """
SELECT
    i.CodItemSol, i.CodSolicitacao, i.DataEntrada, i.DescExames, i.CodConvExames,
    i.NomeTerceirizado, i.Valor, i.VlTerceirizado, i.SituacaoResultado, i.Origem, i.CodTExame,
    s.codpaciente, s.CodConvenio, s.dtaentrada AS Sol_dtaentrada, s.Hora, s.Valortotal,
    s.TipoPgto, s.Obs_Sol, s.Medico,
    p.nome AS PacienteNome, p.cpf AS PacienteCPF, p.datanasc AS PacienteNascimento,
    p.fone AS PacienteFone, p.EmailPac AS PacienteEmail, p.cidade AS PacienteCidade,
    p.uf AS PacienteUF, p.sexo AS PacienteSexo,
    te.CodigoExame AS CodigoExame, te.descricao AS ExameDescricao
FROM dbo.ItemSol i
JOIN dbo.solicitacao s ON s.codsolicitacao = i.CodSolicitacao
LEFT JOIN dbo.paciente p ON p.codpaciente = s.codpaciente
LEFT JOIN dbo.texame te ON te.CodTexame = i.CodTExame
LEFT JOIN dbo._MonitorSent ms ON ms.CodItemSol = i.CodItemSol
WHERE 1 = 1
  {filtro}
ORDER BY i.CodSolicitacao, i.CodItemSol
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="reenfileira despachos a partir desta data (YYYY-MM-DD)")
    ap.add_argument("--sol", help="lista de CodSolicitacao separados por virgula")
    ap.add_argument("--item", help="lista de CodItemSol separados por virgula (envia SO estes)")
    ap.add_argument("--confirmar", action="store_true",
                    help="grava de fato na fila (sem isto, apenas simula)")
    args = ap.parse_args()

    if not args.data and not args.sol and not args.item:
        print("Informe --data, --sol ou --item. Use --help para ver os exemplos.")
        return 1

    filtro, params = "", {}
    if args.item:
        # Itens avulsos: nao exige passagem previa pelo _MonitorSent.
        ids = [int(x.strip()) for x in args.item.split(",") if x.strip()]
        filtro += " AND i.CodItemSol IN (" + ",".join(str(i) for i in ids) + ")"
    else:
        # Reenvio de lotes ja despachados.
        filtro += " AND ms.Destino LIKE '%Bemsoft%'"
        if args.data:
            filtro += " AND CAST(ms.EnviadoEm AS date) >= :data"
            params["data"] = args.data
        if args.sol:
            ids = [int(x.strip()) for x in args.sol.split(",") if x.strip()]
            filtro += " AND i.CodSolicitacao IN (" + ",".join(str(i) for i in ids) + ")"

    bemsoft_set = set(config.TERCEIROS)

    with database.ENGINE.begin() as conn:
        rows = conn.execute(text(SQL_ITENS.format(filtro=filtro)), params).mappings().all()

    if not rows:
        print("Nenhum item encontrado para os filtros informados.")
        return 0

    grupos = {}
    for r in rows:
        # Só itens que realmente pertencem ao Bemsoft — os de imagem foram por outro caminho.
        if r["NomeTerceirizado"] not in bemsoft_set:
            continue
        g = grupos.setdefault(r["CodSolicitacao"], {"head": r, "items": []})
        g["items"].append(row_to_item(dict(r)))

    if not grupos:
        print("Nenhum item de laboratorio nos filtros informados.")
        return 0

    modo = "GRAVANDO NA FILA" if args.confirmar else "SIMULACAO (nada sera gravado)"
    print(f"=== {modo} ===")
    print(f"{len(grupos)} solicitacao(oes), "
          f"{sum(len(g['items']) for g in grupos.values())} item(ns) de laboratorio\n")

    enfileirados = 0
    for cod, g in sorted(grupos.items()):
        nome = str(g["head"]["PacienteNome"] or "").strip()
        # Mesmo agrupamento do worker: um lote por data de coleta.
        for lote in _split_por_data_coleta(g["items"]):
            dia = str(lote[0].get("DataEntrada") or "")[:10]
            print(f"  sol={cod:<7} {nome[:38]:<38} {len(lote):>3} item(ns)  coleta={dia}")
            if args.confirmar:
                evento = build_group_event(g["head"], lote)
                if bemsoft_api.persist_pending(evento, reason="reenfileirado manualmente"):
                    enfileirados += 1

    print()
    if args.confirmar:
        print(f"{enfileirados} evento(s) na fila: {bemsoft_api._get_pending_dir()}")
        print("O worker reenvia no proximo ciclo. Acompanhe completo/logs/envios_*.txt.")
    else:
        print("Nada foi gravado. Repita com --confirmar para enfileirar de verdade.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
