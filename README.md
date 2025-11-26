# Monitor SQL → Bemsoft (all‑in‑one)

Integração que lê itens de exames de um banco SQL Server, agrupa por solicitação e envia pedidos para a API da Bemsoft (`POST /requests`). Roda em loop (daemon/worker), com checkpoint incremental, retries, idempotência e persistência de falhas para reprocessamento.

Documentação BemSoft: https://bemsoft.ws.wiselab.com.br/swagger


## Visão geral (o que faz hoje)

- Lê novos registros da tabela `ItemSol` (join com `solicitacao` e `paciente`) filtrando por `NomeTerceirizado`.
- Usa um checkpoint persistente (`dbo._MonitorState.LastItemId`) para processar somente itens novos.
- Debounce opcional para aguardar a solicitação “assentar” antes de enviar.
- Agrupa linhas por `CodSolicitacao` e monta 1 payload por solicitação.
- Resolve `supportSpecimenId` consultando e cacheando o catálogo `GET /tests` da Bemsoft.
- Suporta mapeamento local de códigos de exame → `supportTestId` via arquivo JSON.
- Envia `POST /requests` com `Idempotency-Key` baseada em `CodSolicitacao` e com retries/backoff.
- Salva falhas em disco (`FAILED_DIR`) para reenvio manual.
- Modo `DRY_RUN` para validar transformação e payload sem fazer chamadas HTTP.

Fluxo resumido: SQL Server → transformar → (cache `/tests`) → POST `/requests` → checkpoint atualizado → falhas em `completo/failed_events/` (se houver).

## Requisitos

- Python 3.10+
- Pacotes Python: `requests`, `urllib3`, `sqlalchemy`, `pyodbc`, `python-dotenv`
- SQL Server acessível e driver ODBC instalado (recomendado: “ODBC Driver 18 for SQL Server”).

Observação (Windows): instale o driver ODBC 18 e o pacote `pyodbc`. No Linux, garanta `unixODBC` e o driver MS ODBC correspondentes.

## Configuração (.env)

Todas as variáveis são lidas de um arquivo `.env` na raiz. Principais chaves:

- Banco de dados
  - `DB_SERVER`: ex. `localhost\SQLEXPRESS` ou `10.0.0.5\SQLEXPRESS`
  - `DB_NAME`, `DB_USER`, `DB_PASS`
  - `ODBC_DRIVER`: ex. `ODBC Driver 18 for SQL Server`

- Leitura/execução
  - `POLL_SECONDS`: intervalo de polling (segundos)
  - `DEBOUNCE_SECONDS`: atraso (em segundos) antes do envio; ex.: `300` = espera 5 minutos (0 desliga)
  - `TERCEIROS`: lista separada por vírgula com os nomes em `ItemSol.NomeTerceirizado` (ex.: `DIAGNÓSTICO DO BRASIL - DB,AME-SE - PARDINI`)
  - `TERCEIRO`: opção legada (um único nome); se definido, será usado como fallback
  - `FAILED_DIR`: pasta onde salvar falhas (padrão `completo/failed_events`)

- Bemsoft
  - `BEMSOFT_BASE_URL`: ex. `https://bemsoft.ws.wiselab.com.br`
  - `BEMSOFT_ENDPOINT`: ex. `/requests`
  - `BEMSOFT_TOKEN`: token Bearer de produção (obrigatório se `DRY_RUN=0`)
  - `BEMSOFT_TIMEOUT`, `BEMSOFT_RETRIES`, `BEMSOFT_BACKOFF`, `BEMSOFT_VERIFY`
  - `BEMSOFT_DRY_RUN`: `1` para não enviar (somente gerar payload), `0` para enviar

- Defaults de dados (usados quando o legado não fornece)
  - `DEFAULT_GENDER`: `M` ou `F` (obrigatório se não vier do paciente)
  - `DEFAULT_BIRTHDATE`: `YYYY-MM-DD` (obrigatório se não vier do paciente)

- Médico (opcional – envia somente se todos estiverem preenchidos)
  - `PHYSICIAN_NAME`, `PHYSICIAN_COUNCIL`, `PHYSICIAN_NUMBER`, `PHYSICIAN_UF`

- Mapeamento de exames (opcional)
  - `BEMSOFT_TEST_MAP_PATH`: caminho para um JSON com `{ "<codigo_local>": "<supportTestId>" }`

Você pode começar copiando o arquivo de exemplo e ajustando:

```
cp .env.example .env    # Linux/macOS
REM copy .env.example .env  # Windows (cmd)
```

Exemplo mínimo de `.env` (sanitizado):

```
DB_SERVER=localhost\SQLEXPRESS
DB_NAME=MinhaBase
DB_USER=usuario
DB_PASS=senha
ODBC_DRIVER=ODBC Driver 18 for SQL Server

POLL_SECONDS=5
DEBOUNCE_SECONDS=300
TERCEIROS=DIAGNÓSTICO DO BRASIL - DB,AME-SE - PARDINI,AME-SE LABORATORIO

BEMSOFT_BASE_URL=https://bemsoft.ws.wiselab.com.br
BEMSOFT_ENDPOINT=/requests
BEMSOFT_TOKEN=coloque_seu_token_aqui
BEMSOFT_DRY_RUN=1

DEFAULT_GENDER=M
DEFAULT_BIRTHDATE=1970-01-01
```

Exemplo de arquivo de mapeamento (`tests_map.json`):

```
{
  "HEMOGRAMA": "HB-001",
  "GLICOSE": "GLU-FAST",
  "12345": "TEST-12345"
}
```

Depois, aponte `BEMSOFT_TEST_MAP_PATH=./tests_map.json` no `.env`.

## Como rodar

1) Crie e ative um ambiente virtual (opcional):

```
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS
```

2) Instale as dependências:

```
pip install -r requirements.txt
```

3) Configure o `.env` conforme sua infraestrutura.

4) Execute o monitor:

```
python main.py
```

Mensagens de log no console mostram o evento agrupado por solicitação e o resultado do envio. Com `BEMSOFT_DRY_RUN=1`, apenas imprime o payload gerado (sem enviar).

Atalhos (scripts prontos em `scripts/`):

- Linux/macOS: `bash scripts/start_monitor.sh` e `bash scripts/stop_monitor.sh`
- Windows: `scripts\start_monitor.bat` e `scripts\stop_monitor.bat`

## Gerar executável e instalar como serviço Windows

Para rodar automaticamente no servidor de produção, você pode gerar um executável standalone e instalá-lo como serviço Windows.

### 1. Gerar o executável

Na máquina de desenvolvimento (com o código-fonte):

```batch
build.bat
```

Este script vai:
- Instalar o PyInstaller automaticamente
- Gerar o arquivo `dist\BemsoftMonitor.exe` (executável único)
- Incluir todas as dependências necessárias

### 2. Preparar para deploy

Copie os seguintes arquivos para o servidor:

```
BemsoftMonitor.exe  (do diretório dist/)
.env                (configurado com as credenciais do servidor)
install_service.bat
uninstall_service.bat
```

Opcionalmente, copie também o `nssm.exe` (baixe de [nssm.cc](https://nssm.cc/download)) para a mesma pasta.

### 3. Instalar como serviço Windows

No servidor, execute como **Administrador**:

```batch
install_service.bat
```

Isso vai:
- Verificar se o NSSM está instalado (necessário para gerenciar serviços)
- Criar o serviço "BemsoftMonitor"
- Configurar para iniciar automaticamente com o Windows
- Criar logs em `logs\service_output.log` e `logs\service_error.log`
- Iniciar o serviço imediatamente

### 4. Gerenciar o serviço

Comandos úteis (executar como Administrador):

```batch
# Ver status
sc query BemsoftMonitor

# Parar
sc stop BemsoftMonitor

# Iniciar
sc start BemsoftMonitor

# Ver logs em tempo real
type logs\service_output.log
```

Ou use o gerenciador de serviços do Windows (`services.msc`).

### 5. Desinstalar

Para remover o serviço, execute como **Administrador**:

```batch
uninstall_service.bat
```

### Requisitos para o servidor

O servidor Windows precisa ter instalado:
- **ODBC Driver 18 for SQL Server** (ou outra versão configurada no `.env`)
- **Visual C++ Redistributable** (geralmente já instalado)
- O executável já inclui Python e todas as bibliotecas

### Troubleshooting

- **Erro de permissão**: Execute os scripts como Administrador
- **NSSM não encontrado**: Baixe de [nssm.cc](https://nssm.cc/download) e coloque `nssm.exe` na mesma pasta
- **Serviço não inicia**: Verifique os logs em `logs\service_error.log`
- **Erro de conexão SQL**: Verifique o `.env` e se o ODBC Driver está instalado
- **Arquivo .env não encontrado**: O `.env` deve estar na mesma pasta do executável

## Reprocessar falhas (retry)

Use o script `retry_failed.py` para reenviar eventos salvos em `FAILED_DIR`.

- Dry-run (padrão, não envia):

```
python retry_failed.py --dir completo/failed_events
```

- Enviar de fato (override `BEMSOFT_DRY_RUN=0` neste processo):

```
python retry_failed.py --dir completo/failed_events --send
```

- Processar um arquivo específico e mover os enviados com sucesso:

```
python retry_failed.py --file completo/failed_events/20240101T120000Z_123.json --send --move-ok completo/sent
```

- Limitar a N arquivos e mostrar detalhes de resposta:

```
python retry_failed.py --limit 10 --send --verbose
```

Atalhos (scripts):

- Linux/macOS: `bash scripts/start_retry.sh [completo/failed_events]` e `bash scripts/stop_retry.sh`
- Windows: `scripts\start_retry.bat` e `scripts\stop_retry.bat`

## Detalhes de funcionamento

- Checkpoint incremental: tabela `dbo._MonitorState` é criada automaticamente (se não existir) e armazena `LastItemId`. O monitor lê sempre itens com `CodItemSol > LastItemId`.
- Agrupamento por solicitação: todas as linhas com o mesmo `CodSolicitacao` são agregadas em um único payload de pedido.
- Janela de debounce: cada solicitação detectada entra em uma fila in-memory e só é enviada após `DEBOUNCE_SECONDS` segundos (logs `[debounce]` indicam o tempo restante e a quantidade na fila).
- Datas/horários: prioriza `solicitacao.dtaentrada` + `Hora`; se não disponíveis, tenta `ItemSol.DataEntrada`; por fim usa o horário atual (fuso −03:00).
- Paciente: gera `externalId` estável com base em `codpaciente` ou CPF; exige `birthDate` e `gender` (ou usa os defaults do `.env`).
- Exames (tests):
  - `supportTestId` vem do código local mapeado (arquivo JSON) ou do próprio `CodConvExames`.
  - `supportSpecimenId` é resolvido pelo catálogo `GET /tests` (cacheado em memória). No `DRY_RUN`, é usado um valor dummy (`SPECIMEN-TEST`).
- Envio para Bemsoft:
  - Cabeçalhos: `Authorization: Bearer <TOKEN>` e `Idempotency-Key: sol-<CodSolicitacao>`.
  - Retry e backoff automáticos para 502/503/504.
  - Respeita `BEMSOFT_VERIFY` para verificação TLS.
- Falhas: qualquer erro de transformação/envio gera um arquivo JSON em `FAILED_DIR` com o motivo e o evento completo para posterior reenvio.

## Reprocessando falhas manualmente

Para reenviar um evento salvo em `FAILED_DIR`, você pode usar um REPL Python:

```
python
>>> import json
>>> from bemsoft_api import send_to_bemsoft
>>> data = json.load(open('completo/failed_events/20240101T120000Z_123.json', encoding='utf-8'))
>>> send_to_bemsoft(data['event'])
```

Garanta `BEMSOFT_DRY_RUN=0` e `BEMSOFT_TOKEN` válidos para que o envio ocorra.

## Solução de problemas

- Conexão ODBC: confirme o driver (`ODBC Driver 18 for SQL Server`) instalado e credenciais válidas.
- Certificado/TLS: ajuste `BEMSOFT_VERIFY=0` apenas para teste (não recomendado em produção).
- Catálogo `/tests`: é necessário `BEMSOFT_TOKEN` para carregar; sem ele e fora do `DRY_RUN`, a resolução de `supportSpecimenId` falhará.
- `supportSpecimenId ausente`: ajuste seu mapeamento (`BEMSOFT_TEST_MAP_PATH`) ou valide o catálogo da Bemsoft.

## Estrutura do projeto

- `main.py`: script principal (poll, transformação, envio, retries, falhas).
- `retry_failed.py`: utilitário CLI para reprocessar eventos com falha.
- `.env`: configurações locais (não commitar segredos reais em repositórios públicos).
- `completo/failed_events/`: diretório (criado automaticamente) para eventos que falharam.

## Rodar como serviço

### Windows (NSSM)

1. Baixe e instale o NSSM (Non-Sucking Service Manager).
2. Execute:

```
nssm install BemsoftMonitor "C:\\Path\\to\\python.exe" "C:\\Path\\to\\project\\main.py"
```

3. Em “Startup directory”, aponte para a pasta do projeto. Garanta que o `.env` esteja na raiz do projeto e acessível pelo serviço.
4. Inicie o serviço pelo Services.msc: `BemsoftMonitor`.

Para o reprocessador de falhas, você pode criar outro serviço apontando para `retry_failed.py --send` se desejar reprocessamento contínuo (não recomendado em paralelo com o monitor sem coordenação).

### Linux (systemd)

Arquivo de unidade exemplo (`/etc/systemd/system/bemsoft-monitor.service`):

```
[Unit]
Description=Bemsoft Monitor (SQL -> Bemsoft)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/bemsoft-monitor
ExecStart=/usr/bin/python3 /opt/bemsoft-monitor/main.py
Restart=on-failure
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Comandos:

```
sudo systemctl daemon-reload
sudo systemctl enable bemsoft-monitor
sudo systemctl start bemsoft-monitor
sudo systemctl status bemsoft-monitor
```

Garanta que o `.env` exista em `/opt/bemsoft-monitor/.env` e o diretório tenha permissões corretas.

---

