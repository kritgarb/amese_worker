"""
Script para testar conexão com banco de dados e APIs
Execute este script para verificar se todas as dependências estão funcionando
"""
import sys
from pathlib import Path

# Adiciona src ao path
ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

print("=" * 60)
print("  Teste de Conexões - DB API Monitor")
print("=" * 60)
print()

# Teste 1: Importar módulos
print("[1/6] Testando importação de módulos...")
try:
    import config
    import database
    import bemsoft_api
    import sheets_client
    print("✅ Todos os módulos importados com sucesso")
except Exception as e:
    print(f"❌ Erro ao importar módulos: {e}")
    sys.exit(1)

print()

# Teste 2: Verificar variáveis de ambiente
print("[2/6] Verificando variáveis de ambiente...")
issues = []

if not config.SERVER:
    issues.append("❌ DB_SERVER não configurado")
else:
    print(f"✅ DB_SERVER: {config.SERVER}")

if not config.DB:
    issues.append("❌ DB_NAME não configurado")
else:
    print(f"✅ DB_NAME: {config.DB}")

if not config.TOKEN:
    issues.append("⚠️  BEMSOFT_TOKEN não configurado (DRY_RUN deve estar ativado)")
else:
    print(f"✅ BEMSOFT_TOKEN: {'*' * 20}")

if not config.GOOGLE_API_KEY:
    issues.append("⚠️  GOOGLE_API_KEY não configurado")
else:
    print(f"✅ GOOGLE_API_KEY: {'*' * 20}")

if not config.GOOGLE_SHEET_ID:
    issues.append("⚠️  GOOGLE_SHEET_ID não configurado")
else:
    print(f"✅ GOOGLE_SHEET_ID: {config.GOOGLE_SHEET_ID[:20]}...")

if issues:
    print()
    for issue in issues:
        print(issue)

print()

# Teste 3: Verificar drivers ODBC
print("[3/6] Verificando drivers ODBC disponíveis...")
try:
    import pyodbc
    drivers = pyodbc.drivers()
    print(f"✅ Drivers encontrados: {len(drivers)}")
    for driver in drivers:
        marker = "✓" if driver == config.DRIVER else " "
        print(f"  [{marker}] {driver}")

    if config.DRIVER not in drivers:
        print(f"⚠️  Driver configurado '{config.DRIVER}' não encontrado!")
        print("   Considere usar um dos drivers listados acima")
except Exception as e:
    print(f"❌ Erro ao verificar drivers: {e}")

print()

# Teste 4: Testar conexão com banco de dados
print("[4/6] Testando conexão com banco de dados...")
try:
    with database.ENGINE.begin() as conn:
        result = conn.execute(database.text("SELECT @@VERSION")).scalar()
        print(f"✅ Conexão estabelecida com sucesso!")
        print(f"   SQL Server: {result[:100]}...")

        # Testa tabela de estado
        last_id = conn.execute(database.SQL_GET_LAST).scalar()
        print(f"✅ Tabela de estado acessível (last_id={last_id or 0})")

except Exception as e:
    print(f"❌ Erro ao conectar ao banco de dados:")
    print(f"   {type(e).__name__}: {e}")
    print()
    print("   Possíveis soluções:")
    print("   - Verifique se SQL Server está acessível")
    print("   - Verifique credenciais no .env")
    print("   - Verifique se o serviço tem permissão de acesso")
    print("   - Tente adicionar TrustServerCertificate=yes na connection string")

print()

# Teste 5: Testar Google Sheets API
print("[5/6] Testando Google Sheets API...")
if config.GOOGLE_API_KEY and config.GOOGLE_SHEET_ID:
    try:
        # Tenta carregar o cache do Google Sheets
        test_info = sheets_client.get_test_info("GLI")
        if test_info:
            print(f"✅ Google Sheets acessível")
            print(f"   Exemplo GLI: {test_info}")
        else:
            print(f"⚠️  Google Sheets acessível mas 'GLI' não encontrado")
    except Exception as e:
        print(f"❌ Erro ao acessar Google Sheets:")
        print(f"   {type(e).__name__}: {e}")
else:
    print("⏭️  Pulando (credenciais não configuradas)")

print()

# Teste 6: Testar Bemsoft API (apenas estrutura, não envia)
print("[6/6] Testando estrutura Bemsoft API...")
if config.TOKEN and not config.DRY_RUN:
    try:
        session = bemsoft_api._build_session()
        print(f"✅ Sessão HTTP criada")
        print(f"   Base URL: {config.BASE_URL}")
        print(f"   Endpoint: {config.REQS_ENDPOINT}")
        print(f"   Timeout: {config.TIMEOUT}s")
        session.close()
    except Exception as e:
        print(f"❌ Erro ao criar sessão HTTP:")
        print(f"   {type(e).__name__}: {e}")
else:
    print(f"⏭️  Pulando (DRY_RUN={config.DRY_RUN})")

print()
print("=" * 60)
print("  Teste concluído!")
print("=" * 60)
print()
print("Se todos os testes passaram (✅), o serviço deve funcionar.")
print("Se houver erros (❌), corrija-os antes de iniciar o serviço.")
print()
