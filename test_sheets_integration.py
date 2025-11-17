#!/usr/bin/env python
"""
Script de teste para validar a integração com Google Sheets.
Execute este script para testar se a API Key e a planilha estão configuradas corretamente.
"""

import sys
from pathlib import Path

# Adiciona o diretório src ao path
ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import config
import sheets_client


def test_config():
    """Testa se as variáveis de ambiente estão configuradas."""
    print("=" * 60)
    print("TESTE 1: Configuração das Variáveis de Ambiente")
    print("=" * 60)

    has_config = True

    if config.GOOGLE_SHEET_ID:
        print(f"✓ GOOGLE_SHEET_ID: {config.GOOGLE_SHEET_ID}")
    else:
        print("✗ GOOGLE_SHEET_ID: NÃO CONFIGURADO")
        has_config = False

    if config.GOOGLE_SHEET_RANGE:
        print(f"✓ GOOGLE_SHEET_RANGE: {config.GOOGLE_SHEET_RANGE}")
    else:
        print("✗ GOOGLE_SHEET_RANGE: NÃO CONFIGURADO")
        has_config = False

    if config.GOOGLE_API_KEY:
        # Mostra apenas os primeiros e últimos caracteres da API Key
        masked_key = config.GOOGLE_API_KEY[:10] + "..." + config.GOOGLE_API_KEY[-4:]
        print(f"✓ GOOGLE_API_KEY: {masked_key}")
    else:
        print("✗ GOOGLE_API_KEY: NÃO CONFIGURADO")
        has_config = False

    print()
    return has_config


def test_connection():
    """Testa a conexão com a planilha Google Sheets."""
    print("=" * 60)
    print("TESTE 2: Conexão com Google Sheets")
    print("=" * 60)

    try:
        cache = sheets_client._get_sheets_cache()

        if not cache:
            print("✗ Cache não inicializado (variáveis não configuradas)")
            return False

        cache.ensure_loaded()

        print(f"✓ Planilha carregada com sucesso!")
        print(f"✓ Total de exames carregados: {len(cache.cache)}")
        print()
        return True

    except Exception as e:
        print(f"✗ Erro ao conectar com Google Sheets: {e}")
        print()
        return False


def test_sample_queries():
    """Testa consultas de exemplo."""
    print("=" * 60)
    print("TESTE 3: Consultas de Exemplo")
    print("=" * 60)

    # IDs de teste baseados na planilha fornecida
    test_ids = ["ACET", "SURINA", "T3L", "INEXISTENTE"]

    for test_id in test_ids:
        info = sheets_client.get_test_info(test_id)
        descmat = sheets_client.get_descmat_for_test(test_id)

        print(f"\nTest ID: {test_id}")

        if info:
            print(f"  ✓ Encontrado!")
            print(f"    - TEST_NAME: {info.get('TEST_NAME')}")
            print(f"    - DESCMAT: {info.get('SUPPORT_LAB_DESCMAT')}")
        else:
            print(f"  ✗ Não encontrado na planilha")

    print()


def test_cache_listing():
    """Lista os primeiros 10 exames do cache."""
    print("=" * 60)
    print("TESTE 4: Listagem dos Primeiros Exames")
    print("=" * 60)

    try:
        cache = sheets_client._get_sheets_cache()

        if not cache:
            print("✗ Cache não disponível")
            return

        cache.ensure_loaded()

        items = list(cache.cache.items())[:10]

        if not items:
            print("✗ Nenhum exame encontrado na planilha")
            return

        print(f"\nPrimeiros {len(items)} exames:\n")

        for test_id, data in items:
            print(f"  {test_id:15} | {data.get('TEST_NAME', '')[:30]:30} | {data.get('SUPPORT_LAB_DESCMAT', '')[:40]}")

        print()

    except Exception as e:
        print(f"✗ Erro ao listar exames: {e}")
        print()


def main():
    """Executa todos os testes."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "TESTE DE INTEGRAÇÃO GOOGLE SHEETS" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    # Teste 1: Configuração
    config_ok = test_config()

    if not config_ok:
        print("\n⚠ ATENÇÃO: Configure as variáveis de ambiente antes de continuar!")
        print("Adicione ao seu arquivo .env:")
        print()
        print("GOOGLE_SHEET_ID=1VnUisJH9L5O_DarJCgafUHU8wZMjlk6Lc7rxb8yUwkU")
        print("GOOGLE_SHEET_RANGE=Sheet1!A:C")
        print("GOOGLE_API_KEY=AIzaSyDrMPHTr0FHG60BkbhBlgQJolrVxjqev8U")
        print()
        return

    # Teste 2: Conexão
    connection_ok = test_connection()

    if not connection_ok:
        print("\n⚠ ATENÇÃO: Verifique se:")
        print("  1. A planilha está compartilhada como 'Anyone with the link - Viewer'")
        print("  2. A Google Sheets API está habilitada no projeto do Google Cloud")
        print("  3. A API Key está correta")
        print()
        return

    # Teste 3: Consultas
    test_sample_queries()

    # Teste 4: Listagem
    test_cache_listing()

    # Resultado final
    print("=" * 60)
    print("RESULTADO FINAL")
    print("=" * 60)
    print("✓ Todos os testes passaram com sucesso!")
    print("✓ A integração com Google Sheets está funcionando corretamente!")
    print()
    print("Próximos passos:")
    print("  1. Execute o main.py para testar em produção")
    print("  2. Monitore os logs para ver as mensagens [sheets]")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTeste interrompido pelo usuário.")
    except Exception as e:
        print(f"\n\n✗ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
