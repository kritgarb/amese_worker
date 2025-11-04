# Mapeamento: Do Banco para a API Bemsoft

Este documento explica de onde vem cada dado que enviamos para a API da Bemsoft.

---

## Como Funciona

1. Pegamos dados de 3 tabelas do banco Ame-se
2. Transformamos em um formato que a Bemsoft entende
3. Enviamos via API para o endpoint /requests

---

## Estrutura do Payload (O que enviamos)

```json
{
  "batch": {
    "externalId": "sol-4497",
    "date": "2025-07-01",
    "time": "08:00:00",
    "order": {
      "externalId": "order-4497",
      "date": "2025-07-01",
      "time": "08:00:00",
      "patient": { ... },
      "physician": { ... },
      "tests": [ ... ]
    }
  }
}
```

---

## Mapeamento Completo - BATCH

O `batch` é o "lote" que agrupa uma ordem/solicitação.

| Campo no Payload | De onde vem | Exemplo |
|-----------------|-------------|---------|
| `batch.externalId` | `Ame-se.solicitacao.codsolicitacao` | `"sol-4497"` |
| `batch.date` | `Ame-se.solicitacao.dtaentrada` | `"2025-07-01"` |
| `batch.time` | `Ame-se.solicitacao.Hora` | `"08:00:00"` |

### Explicação:
- Pegamos o **código da solicitação** do banco
- Pegamos a **data e hora de entrada** da solicitação
- Transformamos em formato que a Bemsoft aceita

---

## Mapeamento Completo - ORDER

A `order` é a "ordem médica" com os dados do paciente e exames.

| Campo no Payload | De onde vem | Exemplo |
|-----------------|-------------|---------|
| `order.externalId` | `Ame-se.solicitacao.codsolicitacao` | `"order-4497"` |
| `order.date` | `Ame-se.solicitacao.dtaentrada` | `"2025-07-01"` |
| `order.time` | `Ame-se.solicitacao.Hora` | `"08:00:00"` |
| `order.patientHeight` | *(não temos no banco)* | `0` |
| `order.patientWeight` | *(não temos no banco)* | `0` |

### Explicação:
- A ordem tem os **mesmos dados do batch** (data, hora, código)
- Altura e peso do paciente **não estão no banco**, então enviamos `0`

---

## Mapeamento Completo - PATIENT

Os dados do paciente dentro da `order`.

| Campo no Payload | De onde vem | Transformação | Exemplo |
|-----------------|-------------|---------------|---------|
| `patient.externalId` | `Ame-se.paciente.codpaciente` | Vira `"pat-3384"` | `"pat-3384"` |
| | *(ou se não tiver)* `Ame-se.paciente.cpf` | Vira `"cpf-12345678900"` | `"cpf-00000000000"` |
| `patient.name` | `Ame-se.paciente.nome` | - | `"LAYNE GRAZIELLE MATIAS ALVES"` |
| `patient.birthDate` | `Ame-se.paciente.datanasc` | Formato `YYYY-MM-DD` | `"1990-05-15"` |
| | *(se for NULL)* `.env → DEFAULT_BIRTHDATE` | - | `"1970-01-01"` |
| `patient.gender` | `Ame-se.paciente.sexo` | `"Feminino"` → `"F"` | `"F"` |
| | | `"Masculino"` → `"M"` | `"M"` |
| | *(se for NULL)* `.env → DEFAULT_GENDER` | - | `"M"` |
| `patient.weight` | *(não temos no banco)* | - | `0` |
| `patient.height` | *(não temos no banco)* | - | `0` |

### Explicação:
- **externalId**: Usamos o código do paciente ou CPF como identificador único
- **name**: Nome completo do paciente
- **birthDate**: Data de nascimento (se não tiver, usa `1970-01-01` do `.env`)
- **gender**: Convertemos "Feminino"/"Masculino" para "F"/"M" (se não tiver, usa o padrão do `.env`)
- **weight/height**: Não temos esses dados, então enviamos `0`

---

## Mapeamento Completo - PHYSICIAN (Opcional)

Dados do médico solicitante. **Só enviamos se estiver configurado no `.env`**

| Campo no Payload | De onde vem | Exemplo |
|-----------------|-------------|---------|
| `physician.externalId` | `.env → PHYSICIAN_NUMBER` | `"123456"` |
| `physician.name` | `.env → PHYSICIAN_NAME` | `"NAO INFORMADO"` |
| `physician.councilAbbreviation` | `.env → PHYSICIAN_COUNCIL` | `"CRM"` |
| `physician.councilNumber` | `.env → PHYSICIAN_NUMBER` | `"123456"` |
| `physician.councilUf` | `.env → PHYSICIAN_UF` | `"SE"` |

### Explicação:
- Como o banco **não tem dados do médico**, pegamos do arquivo `.env`
- Se **não estiver configurado no `.env`**, não enviamos o bloco `physician`

---

## Mapeamento Completo - TESTS (Array de Exames)

Cada item do array `tests` representa **um exame** da solicitação.

| Campo no Payload | De onde vem | Transformação | Exemplo |
|-----------------|-------------|---------------|---------|
| `test.externalId` | `Ame-se.ItemSol.CodItemSol` | Vira `"item-17065"` | `"item-17065"` |
| `test.collectionDate` | `Ame-se.ItemSol.DataEntrada` | Formato `YYYY-MM-DD` | `"2025-10-27"` |
| `test.collectionTime` | `Ame-se.ItemSol.DataEntrada` | Formato `HH:MM:SS` | `"23:45:56"` |
| `test.supportTestId` | `Ame-se.ItemSol.CodConvExames` | Pode ser mapeado* | `"FE"` |
| `test.supportSpecimenId` | **API Bemsoft `/tests`** | Busca automática** | `"SORO"` |
| `test.additionalInformations` | Informações extras | Array de chave-valor | *(veja abaixo)* |
| `test.condition` | *(não temos)* | String vazia | `""` |
| `test.preservative` | *(não temos)* | String vazia | `""` |
| `test.diuresisVolume` | *(não temos)* | Zero | `0` |
| `test.diuresisTime` | *(não temos)* | Zero | `0` |

### Explicação:
- **externalId**: Código único do item da solicitação
- **collectionDate/Time**: Data e hora que o exame foi coletado
- **supportTestId**: Código do exame (ex: "FE" para Ferro Sérico)
- **supportSpecimenId**: Tipo de amostra (SORO, SANGUE, etc.) - **buscamos automaticamente da API Bemsoft**
- **additionalInformations**: Informações extras que enviamos:

```json
"additionalInformations": [
  {
    "key": "origem",
    "value": "Ame-se.ItemSol.Origem"  // Ex: "Sistema"
  },
  {
    "key": "descricao",
    "value": "Ame-se.ItemSol.DescExames"  // Ex: "FERRO SERICO"
  }
]
```

### Mapeamento de Códigos de Exames

Se o código do exame no banco **não for o mesmo** que a Bemsoft usa, você pode criar um arquivo de mapeamento:

**Arquivo:** `test_map.json`
```json
{
  "FE": "FERRO_SERICO_BEMSOFT",
  "TSH": "TSH_BEMSOFT",
  "T3L": "T3_LIVRE_BEMSOFT"
}
```

Configure no `.env`:
```
BEMSOFT_TEST_MAP_PATH=test_map.json
```

### Busca Automática do Specimen

O código **automaticamente busca** o tipo de amostra (specimen) na API da Bemsoft:

1. Pega o `supportTestId` (ex: "FE")
2. Consulta o endpoint `/tests` da Bemsoft
3. Encontra qual é o `specimenId` para esse teste
4. Adiciona no payload

**Exemplo:**
```
FE (Ferro Sérico) → API retorna → specimenId = "SORO"
```

---

## Fluxo Completo

```
┌─────────────────────────────────────────────────────────────┐
│  1. MONITOR busca novos dados do banco a cada 5 segundos   │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  2. AGRUPA itens da mesma solicitação (debounce 10s)       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  3. BUSCA dados das 3 tabelas:                             │
│     - Ame-se.ItemSol                                       │
│     - Ame-se.solicitacao                                   │
│     - Ame-se.paciente                                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  4. TRANSFORMA dados no formato da Bemsoft                 │
│     - Converte "Feminino" → "F"                            │
│     - Formata datas YYYY-MM-DD                             │
│     - Busca specimenId na API /tests                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  5. ENVIA para API Bemsoft POST /requests                  │
│     (se DRY_RUN=0)                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Exemplo Real

### Dados do Banco:

**Tabela: solicitacao**
```
codsolicitacao: 4497
codpaciente: 3384
dtaentrada: 2025-07-01
Hora: 08:00
```

**Tabela: paciente**
```
codpaciente: 3384
nome: LAYNE GRAZIELLE MATIAS ALVES
sexo: NULL (vai usar DEFAULT_GENDER=M do .env)
datanasc: NULL (vai usar DEFAULT_BIRTHDATE=1970-01-01 do .env)
cpf: 000.000.000-00
```

**Tabela: ItemSol**
```
CodItemSol: 17065
CodSolicitacao: 4497
DataEntrada: 2025-10-27 23:45:56
DescExames: FERRO SERICO
CodConvExames: FE
NomeTerceirizado: DIAGNÓSTICO DO BRASIL - DB
```

### Payload Gerado:

```json
{
  "batch": {
    "externalId": "sol-4497",
    "date": "2025-07-01",
    "time": "08:00:00",
    "order": {
      "externalId": "order-4497",
      "date": "2025-07-01",
      "time": "08:00:00",
      "patientHeight": 0,
      "patientWeight": 0,
      "patient": {
        "externalId": "pat-3384",
        "name": "LAYNE GRAZIELLE MATIAS ALVES",
        "birthDate": "1970-01-01",
        "gender": "M",
        "weight": 0,
        "height": 0
      },
      "physician": {
        "externalId": "123456",
        "name": "NAO INFORMADO",
        "councilAbbreviation": "CRM",
        "councilNumber": "123456",
        "councilUf": "SE"
      },
      "tests": [
        {
          "externalId": "item-17065",
          "collectionDate": "2025-10-27",
          "collectionTime": "23:45:56",
          "supportTestId": "FE",
          "supportSpecimenId": "SORO",
          "additionalInformations": [
            {"key": "origem", "value": "Sistema"},
            {"key": "descricao", "value": "FERRO SERICO"}
          ],
          "condition": "",
          "preservative": "",
          "diuresisVolume": 0,
          "diuresisTime": 0
        }
      ]
    }
  }
}
```

---

## Campos que Usam Fallback

Quando o banco **não tem** o dado, usamos valores padrão do `.env`:

| Campo | Se vier NULL do banco | Usa do .env |
|-------|----------------------|-------------|
| `patient.gender` | `paciente.sexo = NULL` | `DEFAULT_GENDER=M` |
| `patient.birthDate` | `paciente.datanasc = NULL` | `DEFAULT_BIRTHDATE=1970-01-01` |

---

## Resumo Visual

```
BANCO DE DADOS (Ame-se)
├── solicitacao
│   ├── codsolicitacao ────────────► batch.externalId / order.externalId
│   ├── dtaentrada ────────────────► batch.date / order.date
│   └── Hora ──────────────────────► batch.time / order.time
│
├── paciente
│   ├── codpaciente ───────────────► patient.externalId
│   ├── nome ──────────────────────► patient.name
│   ├── datanasc ──────────────────► patient.birthDate
│   └── sexo ──────────────────────► patient.gender (F/M)
│
└── ItemSol
    ├── CodItemSol ────────────────► test.externalId
    ├── DataEntrada ───────────────► test.collectionDate/Time
    ├── CodConvExames ─────────────► test.supportTestId
    ├── DescExames ────────────────► test.additionalInformations
    └── NomeTerceirizado ──────────► (filtro para pegar só DB)

ARQUIVO .env
├── DEFAULT_GENDER ────────────────► patient.gender (se NULL)
├── DEFAULT_BIRTHDATE ─────────────► patient.birthDate (se NULL)
└── PHYSICIAN_* ───────────────────► order.physician

API BEMSOFT /tests
└── specimenId ────────────────────► test.supportSpecimenId
```

---
