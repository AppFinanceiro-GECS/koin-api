#!/usr/bin/env python3
"""
Script de limpeza de uploads antigos.
Remove arquivos com mais de N dias do diretório uploads/.

Uso:
    python scripts/cleanup_uploads.py [--days N] [--dry-run]

Argumentos:
    --days N    Remove arquivos com mais de N dias (padrão: 30)
    --dry-run   Apenas mostra o que seria removido, sem deletar
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path


def get_uploads_dir() -> Path:
    """Retorna o diretório de uploads."""
    script_dir = Path(__file__).parent
    uploads_dir = script_dir.parent / "uploads"
    return uploads_dir


def cleanup_uploads(days: int = 30, dry_run: bool = False) -> dict:
    """
    Remove arquivos de upload com mais de N dias.

    Args:
        days: Número de dias para considerar arquivo como antigo
        dry_run: Se True, apenas lista arquivos sem remover

    Returns:
        Dicionário com estatísticas da limpeza
    """
    uploads_dir = get_uploads_dir()

    if not uploads_dir.exists():
        print(f"Diretório de uploads não existe: {uploads_dir}")
        return {"files_removed": 0, "bytes_freed": 0, "errors": 0}

    cutoff_date = datetime.now() - timedelta(days=days)

    stats = {
        "files_checked": 0,
        "files_removed": 0,
        "bytes_freed": 0,
        "errors": 0,
        "files_skipped": 0,
    }

    mode = "DRY-RUN" if dry_run else "LIMPEZA"
    print(f"\n{'=' * 60}")
    print(f" {mode} DE UPLOADS - Arquivos > {days} dias")
    print(f"{'=' * 60}")
    print(f"Diretório: {uploads_dir}")
    print(f"Data limite: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")

    # Percorrer todos os arquivos no diretório de uploads
    for user_dir in uploads_dir.iterdir():
        if not user_dir.is_dir():
            continue

        # Ignorar arquivos de sistema
        if user_dir.name.startswith("."):
            continue

        print(f"Processando pasta do usuário: {user_dir.name}")

        for file_path in user_dir.iterdir():
            if not file_path.is_file():
                continue

            # Ignorar arquivos de sistema
            if file_path.name.startswith("."):
                continue

            stats["files_checked"] += 1

            try:
                # Obter data de modificação do arquivo
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                file_size = file_path.stat().st_size

                if file_mtime < cutoff_date:
                    if dry_run:
                        print(f"  [SERIA REMOVIDO] {file_path.name}")
                        print(f"    Modificado: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"    Tamanho: {file_size / 1024:.1f} KB")
                    else:
                        print(f"  [REMOVENDO] {file_path.name}")
                        file_path.unlink()

                    stats["files_removed"] += 1
                    stats["bytes_freed"] += file_size
                else:
                    stats["files_skipped"] += 1

            except Exception as e:
                print(f"  [ERRO] {file_path.name}: {e}")
                stats["errors"] += 1

    # Limpar diretórios vazios de usuários
    for user_dir in uploads_dir.iterdir():
        if user_dir.is_dir() and not any(user_dir.iterdir()):
            if dry_run:
                print(f"\n[SERIA REMOVIDO] Diretório vazio: {user_dir}")
            else:
                print(f"\n[REMOVENDO] Diretório vazio: {user_dir}")
                user_dir.rmdir()

    # Resumo
    print(f"\n{'=' * 60}")
    print(" RESUMO")
    print(f"{'=' * 60}")
    print(f"Arquivos verificados: {stats['files_checked']}")
    print(
        f"Arquivos {'que seriam removidos' if dry_run else 'removidos'}: {stats['files_removed']}"
    )
    print(f"Arquivos mantidos: {stats['files_skipped']}")
    print(
        f"Espaço {'que seria liberado' if dry_run else 'liberado'}: {stats['bytes_freed'] / 1024 / 1024:.2f} MB"
    )
    print(f"Erros: {stats['errors']}")
    print(f"{'=' * 60}\n")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Limpa arquivos de upload antigos")
    parser.add_argument(
        "--days", type=int, default=30, help="Remove arquivos com mais de N dias (padrão: 30)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Apenas mostra o que seria removido")

    args = parser.parse_args()

    if args.days < 1:
        print("Erro: --days deve ser pelo menos 1")
        sys.exit(1)

    stats = cleanup_uploads(days=args.days, dry_run=args.dry_run)

    # Exit code baseado em erros
    sys.exit(1 if stats["errors"] > 0 else 0)


if __name__ == "__main__":
    main()
