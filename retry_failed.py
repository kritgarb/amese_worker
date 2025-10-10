"""
Reprocessa eventos que falharam (arquivos JSON) gerados por main.py.

Por padrão lê JSONs em FAILED_DIR (do .env ou default do monitor) e chama
send_to_bemsoft(event). Pode operar em modo dry-run (não envia) ou enviar de
fato (--send), com opção de mover arquivos bem-sucedidos para outra pasta.
"""

import argparse
import glob
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv

# Carrega .env da raiz do projeto
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import config
from bemsoft_api import send_to_bemsoft

DEFAULT_FAILED_DIR = config.FAILED_DIR


def collect_files(directory: str, files: List[str]) -> List[str]:
    paths: List[str] = []
    if files:
        for f in files:
            p = os.path.abspath(f)
            if os.path.isfile(p):
                paths.append(p)
    else:
        pattern = os.path.join(directory, "*.json")
        paths = sorted(glob.glob(pattern))
    return paths


def main():
    parser = argparse.ArgumentParser(description="Reprocessa eventos com falha (JSON)")
    parser.add_argument(
        "--dir",
        dest="directory",
        default=os.getenv("FAILED_DIR", DEFAULT_FAILED_DIR),
        help="Diretório de falhas (padrão: FAILED_DIR do .env)",
    )
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        help="Caminho de arquivo JSON específico (pode repetir)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limita quantidade de arquivos processados (0 = sem limite)",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Envia para a Bemsoft (define BEMSOFT_DRY_RUN=0). Sem esta flag, roda em dry-run.",
    )
    parser.add_argument(
        "--move-ok",
        dest="move_ok",
        default=None,
        help="Se definido, move arquivos com sucesso para este diretório",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Exibe detalhes do resultado da chamada",
    )

    args = parser.parse_args()

    # Controla DRY_RUN via variável de ambiente do próprio processo
    if args.send:
        os.environ["BEMSOFT_DRY_RUN"] = "0"
    else:
        os.environ["BEMSOFT_DRY_RUN"] = "1"

    directory = os.path.abspath(args.directory)
    files = collect_files(directory, args.files or [])
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    if not files:
        print("Nenhum arquivo de falha encontrado.")
        return

    print(f"Reprocessando {len(files)} arquivo(s) em: {directory}")

    if args.move_ok:
        os.makedirs(args.move_ok, exist_ok=True)

    ok_count = 0
    fail_count = 0

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[skip] falha ao ler {path}: {e}")
            fail_count += 1
            continue

        event = data.get("event", data)

        try:
            result = send_to_bemsoft(event)
            ok = bool(result.get("ok"))
            status = result.get("status")
            if ok:
                print(f"[ok] {os.path.basename(path)} (status={status})")
                ok_count += 1
                if args.move_ok:
                    target = os.path.join(args.move_ok, os.path.basename(path))
                    try:
                        shutil.move(path, target)
                    except Exception as e:
                        print(f"[warn] não foi possível mover {path} → {target}: {e}")
            else:
                fail_count += 1
                print(f"[fail] {os.path.basename(path)} (status={status}) → {result.get('error')}")
                if args.verbose:
                    print(result)
        except Exception as e:
            fail_count += 1
            print(f"[error] exceção ao enviar {os.path.basename(path)}: {e}")

    print(f"Concluído. Sucesso: {ok_count} | Falhas: {fail_count}")


if __name__ == "__main__":
    main()
