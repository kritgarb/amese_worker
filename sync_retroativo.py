"""
Envia exames de imagem retroativos direto para o telemed (sem tocar no Bemsoft).
Uso: python sync_retroativo.py
"""
import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import config
import database
import telemed_client
from main import row_to_item, build_group_event, _json_default
from datetime import datetime
from sqlalchemy import text

# IDs a sincronizar — últimos 5 de imagem de ontem ainda não no telemed
CODITEMSOL_IDS = [124662, 124660, 124659, 124656, 124655]

def main():
    print(f"Sincronizando {len(CODITEMSOL_IDS)} exames de imagem retroativos com o telemed...\n")

    ids_placeholder = ", ".join(str(i) for i in CODITEMSOL_IDS)
    sql = text(f"""
        SELECT
            i.CodItemSol, i.CodSolicitacao, i.DataEntrada, i.DescExames, i.CodConvExames,
            i.NomeTerceirizado, i.Valor, i.VlTerceirizado, i.SituacaoResultado, i.Origem,
            i.CodTExame,
            s.codpaciente, s.CodConvenio, s.dtaentrada AS Sol_dtaentrada, s.Hora,
            s.Valortotal, s.TipoPgto, s.Obs_Sol, s.Medico,
            p.nome AS PacienteNome, p.cpf AS PacienteCPF, p.datanasc AS PacienteNascimento,
            p.fone AS PacienteFone, p.EmailPac AS PacienteEmail,
            p.cidade AS PacienteCidade, p.uf AS PacienteUF, p.sexo AS PacienteSexo,
            te.CodigoExame AS CodigoExame, te.descricao AS ExameDescricao
        FROM dbo.ItemSol i
        JOIN dbo.solicitacao s ON s.codsolicitacao = i.CodSolicitacao
        LEFT JOIN dbo.paciente p ON p.codpaciente = s.codpaciente
        LEFT JOIN dbo.texame te ON te.CodTexame = i.CodTExame
        WHERE i.CodItemSol IN ({ids_placeholder})
        ORDER BY i.CodItemSol ASC
    """)

    with database.ENGINE.begin() as conn:
        rows = conn.execute(sql).mappings().all()

    # Agrupa por solicitação
    groups = {}
    for r in rows:
        k = r["CodSolicitacao"]
        if k not in groups:
            groups[k] = {"head": r, "items": []}
        groups[k]["items"].append(row_to_item(r))

    for cod, g in groups.items():
        event = build_group_event(g["head"], g["items"])
        print(f"Enviando solicitação {cod} ({len(g['items'])} item(ns))...")
        result = telemed_client.sync_event(event)
        if result.get("ok"):
            created = result.get("data", {}).get("created", [])
            skipped = result.get("data", {}).get("skipped", [])
            print(f"  OK criado(s): {len(created)}  ja existia(m): {len(skipped)}")
        else:
            print(f"  ✗ erro: {result.get('error')}")

    print("\nConcluído.")

if __name__ == "__main__":
    main()
