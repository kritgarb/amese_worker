from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from urllib.parse import quote_plus

import config
raw_odbc = (
    f"DRIVER={config.DRIVER};"
    f"SERVER={config.SERVER};"                 
    f"DATABASE={config.DB};"
    f"UID={config.USER};PWD={config.PWD};"
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
"""),
text("""
IF OBJECT_ID('dbo._MonitorPending','U') IS NULL
BEGIN
  CREATE TABLE dbo._MonitorPending (
    CodSolicitacao BIGINT NOT NULL PRIMARY KEY,
    ContentHash VARCHAR(64) NOT NULL,
    FirstSeen datetime2 NOT NULL,
    LastChange datetime2 NOT NULL
  );
END;"""),
text("""
IF OBJECT_ID('dbo._MonitorSent','U') IS NULL
BEGIN
  CREATE TABLE dbo._MonitorSent (
    CodItemSol BIGINT NOT NULL PRIMARY KEY,
    CodSolicitacao BIGINT NULL,
    Destino VARCHAR(40) NULL,
    Status VARCHAR(40) NULL,
    EnviadoEm datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
  );
END;"""),
]

# Registra um item como já despachado (ou descartado de forma definitiva).
# É o que permite segurar o LastItemId sem reenviar o que já saiu: o
# LastItemId vira só uma janela de varredura, e esta tabela é a verdade.
SQL_MARK_SENT = text("""
MERGE dbo._MonitorSent AS alvo
USING (SELECT :item AS CodItemSol) AS origem
   ON alvo.CodItemSol = origem.CodItemSol
WHEN NOT MATCHED THEN
  INSERT (CodItemSol, CodSolicitacao, Destino, Status)
  VALUES (:item, :sol, :destino, :status);
""")

# ---------------------------------------------------------------------------
# Janela de edicao: enquanto a solicitacao nao foi despachada, guardamos um hash
# do seu conteudo. Se a atendente edita/inclui/remove um exame, o hash muda e a
# janela de debounce reinicia — o que sai e sempre a versao final.
# FirstSeen/LastChange sao gravados com o relogio da aplicacao (nunca o do SQL),
# para que a comparacao em Python use a mesma referencia.
# ---------------------------------------------------------------------------
SQL_PENDING_GET = text("""
SELECT CodSolicitacao, ContentHash, FirstSeen, LastChange FROM dbo._MonitorPending;
""")

SQL_PENDING_UPSERT = text("""
MERGE dbo._MonitorPending AS alvo
USING (SELECT :sol AS CodSolicitacao) AS origem
   ON alvo.CodSolicitacao = origem.CodSolicitacao
WHEN MATCHED THEN
  UPDATE SET ContentHash = :hash, LastChange = :last_change
WHEN NOT MATCHED THEN
  INSERT (CodSolicitacao, ContentHash, FirstSeen, LastChange)
  VALUES (:sol, :hash, :first_seen, :last_change);
""")

SQL_PENDING_DELETE = text("""
DELETE FROM dbo._MonitorPending WHERE CodSolicitacao = :sol;
""")

SQL_FETCH_TEMPLATE = """
SELECT TOP (500)
    i.CodItemSol, i.CodSolicitacao, i.DataEntrada, i.DescExames, i.CodConvExames,
    i.NomeTerceirizado, i.Valor, i.VlTerceirizado, i.SituacaoResultado, i.Origem,
    i.CodTExame,

    s.codpaciente, s.CodConvenio, s.dtaentrada AS Sol_dtaentrada, s.Hora, s.Valortotal, s.TipoPgto, s.Obs_Sol, s.Medico,

    p.nome AS PacienteNome, p.cpf AS PacienteCPF, p.datanasc AS PacienteNascimento,
    p.fone AS PacienteFone, p.EmailPac AS PacienteEmail, p.cidade AS PacienteCidade, p.uf AS PacienteUF,
    p.sexo AS PacienteSexo,

    te.CodigoExame AS CodigoExame,
    te.descricao AS ExameDescricao
FROM dbo.ItemSol i
JOIN dbo.solicitacao s ON s.codsolicitacao = i.CodSolicitacao
LEFT JOIN dbo.paciente p ON p.codpaciente = s.codpaciente
LEFT JOIN dbo.texame te ON te.CodTexame = i.CodTExame
WHERE
    i.CodItemSol > :last
    AND NOT EXISTS (
        SELECT 1 FROM dbo._MonitorSent ms WHERE ms.CodItemSol = i.CodItemSol
    )
{terceiro_clause}
ORDER BY i.CodItemSol ASC;
"""


def _build_fetch_query(terceiros):
    clause = ""
    params = {}
    terceiros = [t for t in (terceiros or []) if t]
    if terceiros:
        placeholders = []
        for idx, value in enumerate(terceiros):
            key = f"ter{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        if len(placeholders) == 1:
            clause = f"    AND i.NomeTerceirizado = {placeholders[0]}\n"
        else:
            clause = (
                "    AND i.NomeTerceirizado IN (" + ", ".join(placeholders) + ")\n"
            )
    sql = SQL_FETCH_TEMPLATE.format(terceiro_clause=clause)
    return text(sql), params


def fetch_items(conn, last, terceiros):
    stmt, extra_params = _build_fetch_query(terceiros)
    params = {"last": last}
    params.update(extra_params)
    return conn.execute(stmt, params).mappings().all()


def mark_items_sent(conn, itens, cod_solicitacao=None, destino="", status=""):
    """Marca CodItemSol como despachados, para nunca serem reprocessados."""
    for item_id in itens:
        if item_id is None:
            continue
        conn.execute(SQL_MARK_SENT, {
            "item": int(item_id),
            "sol": int(cod_solicitacao) if cod_solicitacao is not None else None,
            "destino": (destino or "")[:40],
            "status": (status or "")[:40],
        })


def pending_load(conn):
    """Estado das solicitacoes aguardando a janela de edicao, por CodSolicitacao."""
    return {
        r["CodSolicitacao"]: {
            "hash": r["ContentHash"],
            "first_seen": r["FirstSeen"],
            "last_change": r["LastChange"],
        }
        for r in conn.execute(SQL_PENDING_GET).mappings().all()
    }


def pending_upsert(conn, cod_solicitacao, content_hash, first_seen, last_change):
    conn.execute(SQL_PENDING_UPSERT, {
        "sol": int(cod_solicitacao),
        "hash": content_hash,
        "first_seen": first_seen,
        "last_change": last_change,
    })


def pending_delete(conn, cod_solicitacao):
    conn.execute(SQL_PENDING_DELETE, {"sol": int(cod_solicitacao)})


def bootstrap_state():
    with ENGINE.begin() as conn:
        for q in SQL_BOOTSTRAP:
            conn.execute(q)
