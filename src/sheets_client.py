import os
import json
from typing import Dict, Optional, Any
from pathlib import Path

import requests

import config


class SheetsCache:
    """Cache para dados do Google Sheets com informações de materiais (DESCMAT)."""

    def __init__(self, sheet_id: str, range_name: str, api_key: str):
        self.sheet_id = sheet_id
        self.range_name = range_name
        self.api_key = api_key
        # Cache: {TEST_ID: {"TEST_NAME": "...", "SUPPORT_LAB_DESCMAT": "..."}}
        self.cache: Dict[str, Dict[str, str]] = {}
        self._loaded = False

    def _build_url(self) -> str:
        """Constrói URL da Google Sheets API v4."""
        base = "https://sheets.googleapis.com/v4/spreadsheets"
        return f"{base}/{self.sheet_id}/values/{self.range_name}?key={self.api_key}"

    def ensure_loaded(self):
        """Carrega dados do Google Sheets se ainda não foram carregados."""
        if self._loaded:
            return

        url = self._build_url()
        try:
            resp = requests.get(url, timeout=30)

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Falha ao carregar Google Sheets ({resp.status_code}): {resp.text}"
                )

            data = resp.json()
            rows = data.get("values", [])

            if not rows:
                print("[sheets] Aviso: Planilha vazia ou sem dados")
                self._loaded = True
                return

            # Assume que a primeira linha é o cabeçalho: TEST_ID, TEST_NAME, SUPPORT_LAB_DESCMAT
            header = rows[0] if rows else []

            # Identifica índices das colunas
            try:
                idx_test_id = header.index("TEST_ID")
                idx_test_name = header.index("TEST_NAME")
                idx_descmat = header.index("SUPPORT_LAB_DESCMAT")
            except ValueError as e:
                raise RuntimeError(
                    f"Cabeçalho da planilha deve conter TEST_ID, TEST_NAME e SUPPORT_LAB_DESCMAT: {e}"
                )

            # Processa linhas de dados (pula cabeçalho)
            for row in rows[1:]:
                if len(row) <= max(idx_test_id, idx_test_name, idx_descmat):
                    # Linha incompleta, pula
                    continue

                test_id = (row[idx_test_id] or "").strip()
                test_name = (row[idx_test_name] or "").strip()
                descmat = (row[idx_descmat] or "").strip()

                if not test_id:
                    continue

                self.cache[test_id.upper()] = {
                    "TEST_NAME": test_name,
                    "SUPPORT_LAB_DESCMAT": descmat
                }

            self._loaded = True
            print(f"[sheets] Carregado {len(self.cache)} exames da planilha Google Sheets")

        except Exception as e:
            raise RuntimeError(f"Erro ao acessar Google Sheets: {e}")

    def get_descmat(self, test_id: Optional[str]) -> Optional[str]:
        """
        Retorna o SUPPORT_LAB_DESCMAT para um TEST_ID.
        Retorna None se não encontrado.
        """
        if not test_id:
            return None

        self.ensure_loaded()

        key = str(test_id).strip().upper()
        entry = self.cache.get(key)

        if not entry:
            return None

        return entry.get("SUPPORT_LAB_DESCMAT") or None

    def get_info(self, test_id: Optional[str]) -> Optional[Dict[str, str]]:
        """
        Retorna informações completas do teste (TEST_NAME e SUPPORT_LAB_DESCMAT).
        Retorna None se não encontrado.
        """
        if not test_id:
            return None

        self.ensure_loaded()

        key = str(test_id).strip().upper()
        return self.cache.get(key)


# Instância global do cache
_SHEETS_CACHE: Optional[SheetsCache] = None


def _get_sheets_cache() -> Optional[SheetsCache]:
    """Retorna a instância do cache de Google Sheets, se configurado."""
    global _SHEETS_CACHE

    if _SHEETS_CACHE is not None:
        return _SHEETS_CACHE

    sheet_id = config.GOOGLE_SHEET_ID
    range_name = config.GOOGLE_SHEET_RANGE
    api_key = config.GOOGLE_API_KEY

    # Se não está configurado, retorna None (validação opcional)
    if not sheet_id or not api_key:
        return None

    if not range_name:
        range_name = "Sheet1!A:C"  # Default

    _SHEETS_CACHE = SheetsCache(sheet_id, range_name, api_key)
    return _SHEETS_CACHE


def get_descmat_for_test(test_id: Optional[str]) -> Optional[str]:
    """
    Busca o SUPPORT_LAB_DESCMAT para um test_id no Google Sheets.
    Retorna None se não configurado ou não encontrado.
    """
    cache = _get_sheets_cache()
    if not cache:
        return None

    return cache.get_descmat(test_id)


def get_test_info(test_id: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Busca informações completas do teste no Google Sheets.
    Retorna None se não configurado ou não encontrado.
    """
    cache = _get_sheets_cache()
    if not cache:
        return None

    return cache.get_info(test_id)
