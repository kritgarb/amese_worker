# Guia Rápido de Deploy - Bemsoft Monitor

Este guia contém os passos essenciais para gerar o executável e instalar no servidor de produção.

## 1. Desenvolvimento → Build (Máquina Local)

```batch
# 1. Certifique-se de estar no diretório do projeto
cd c:\Users\benja\PycharmProjects\db_api

# 2. Execute o build
build.bat

# 3. Aguarde até ver "BUILD CONCLUIDO COM SUCESSO!"
# O executável será gerado em: dist\BemsoftMonitor.exe
```

## 2. Preparar Pacote de Deploy

Crie uma pasta temporária e copie os arquivos necessários:

```
C:\Deploy\BemsoftMonitor\
├── BemsoftMonitor.exe      ← de dist\
├── .env                     ← configurado para produção
├── install_service.bat      ← da raiz do projeto
├── uninstall_service.bat    ← da raiz do projeto
└── nssm.exe (opcional)      ← de nssm.cc/download
```

## 3. Deploy no Servidor

### Via Remote Desktop ou Acesso Físico:

1. Copie a pasta `C:\Deploy\BemsoftMonitor\` para o servidor
   - Caminho sugerido: `C:\Bemsoft\` ou `C:\Program Files\BemsoftMonitor\`

2. Verifique o arquivo `.env`:
   - Credenciais do SQL Server corretas
   - Token da API Bemsoft válido
   - `BEMSOFT_DRY_RUN=0` (para enviar de verdade)

3. **Execute como Administrador**:
   ```batch
   install_service.bat
   ```

4. Verifique se o serviço iniciou:
   ```batch
   sc query BemsoftMonitor
   ```
   Deve mostrar `STATE: 4 RUNNING`

## 4. Verificar Funcionamento

### Logs em Tempo Real

```batch
# Ver saída do serviço
type logs\service_output.log

# Ver erros (se houver)
type logs\service_error.log

# Monitorar em tempo real (PowerShell)
Get-Content logs\service_output.log -Wait -Tail 50
```

### Comandos de Gerenciamento

```batch
# Ver status
sc query BemsoftMonitor

# Parar serviço
sc stop BemsoftMonitor

# Iniciar serviço
sc start BemsoftMonitor

# Ver propriedades
sc qc BemsoftMonitor
```

### Via Gerenciador de Serviços (GUI)

1. Pressione `Win + R`
2. Digite: `services.msc`
3. Procure por: **Bemsoft Monitor - SQL to API**

## 5. Troubleshooting Rápido

### Serviço não inicia

```batch
# 1. Verifique os logs de erro
type logs\service_error.log

# 2. Tente executar manualmente para ver o erro
BemsoftMonitor.exe

# 3. Verifique o .env
notepad .env
```

### Erro de conexão SQL

- Verifique se o **ODBC Driver 18 for SQL Server** está instalado
- Teste a conexão manualmente:
  ```sql
  sqlcmd -S SERVIDOR\INSTANCIA -U usuario -P senha -d BaseDados
  ```

### Erro "NSSM não encontrado"

1. Baixe: https://nssm.cc/download
2. Extraia o `nssm.exe` (versão win64) para a pasta do BemsoftMonitor
3. Execute `install_service.bat` novamente

### Serviço instalado mas não processa dados

1. Verifique se `BEMSOFT_DRY_RUN=0` no `.env`
2. Verifique os logs de saída
3. Teste a API manualmente:
   ```batch
   curl -H "Authorization: Bearer SEU_TOKEN" https://bemsoft.ws.wiselab.com.br/tests
   ```

## 6. Atualizar o Serviço

Para atualizar para uma nova versão:

```batch
# 1. Pare o serviço
sc stop BemsoftMonitor

# 2. Substitua o BemsoftMonitor.exe pelo novo
# (aguarde alguns segundos)

# 3. Inicie o serviço
sc start BemsoftMonitor
```

## 7. Desinstalar

```batch
# Execute como Administrador
uninstall_service.bat
```

## Checklist de Deploy

- [ ] Build gerado com sucesso
- [ ] Arquivo `.env` configurado e testado
- [ ] ODBC Driver instalado no servidor
- [ ] Scripts de instalação copiados
- [ ] Serviço instalado como Administrador
- [ ] Serviço iniciado com sucesso
- [ ] Logs sendo gerados
- [ ] Teste de envio confirmado (verificar API)
- [ ] Monitoramento configurado

## Contatos e Suporte

- Documentação completa: [README.md](README.md)
- API Bemsoft: https://bemsoft.ws.wiselab.com.br/swagger
- Issues: Reportar problemas no repositório

---

**Última atualização:** 2024-11-26
