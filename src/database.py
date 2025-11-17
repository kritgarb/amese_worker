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
""")
]

SQL_FETCH_TEMPLATE = """
SELECT TOP (500)
    i.CodItemSol, i.CodSolicitacao, i.DataEntrada, i.DescExames, i.CodConvExames,
    i.NomeTerceirizado, i.Valor, i.VlTerceirizado, i.SituacaoResultado, i.Origem,

    s.codpaciente, s.CodConvenio, s.dtaentrada AS Sol_dtaentrada, s.Hora, s.Valortotal, s.TipoPgto, s.Obs_Sol,

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


def bootstrap_state():
    with ENGINE.begin() as conn:
        for q in SQL_BOOTSTRAP:
            conn.execute(q)
