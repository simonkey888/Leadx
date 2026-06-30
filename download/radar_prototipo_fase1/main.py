"""
main.py — Entry point del Radar de Oportunidades (Fase 1).

Uso:
    python main.py                # ejecuta pipeline end-to-end con mock data
    python main.py --review       # lanza CLI de revisión
    python main.py --review --demo  # CLI en modo demo (no interactivo)
    python main.py --sheet-real   # sync real a Google Sheet (requiere credenciales)
    python main.py --help         # ayuda

Requisitos:
    Python 3.10+
    Sólo stdlib para Fase 1 (gspread opcional para sheet real)
"""
from __future__ import annotations
import argparse
import sys

from pipeline import RadarPipeline
from review_cli import ReviewCLI


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="radar",
        description="Radar de Oportunidades — Prototipo Fase 1",
    )
    parser.add_argument(
        "--review", action="store_true",
        help="Lanza CLI de revisión humana en vez del pipeline",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="En modo --review, ejecuta demo automática (no interactivo)",
    )
    parser.add_argument(
        "--sheet-real", action="store_true",
        help="Habilita sync real a Google Sheet (requiere GOOGLE_SERVICE_ACCOUNT_FILE)",
    )
    parser.add_argument(
        "--no-mock", action="store_true",
        help="Usa fuentes reales en vez de mock (Fase 2/3, requiere conectores implementados)",
    )
    args = parser.parse_args()

    if args.review:
        cli = ReviewCLI()
        if args.demo:
            cli.run_demo() if hasattr(cli, "run_demo") else None
            # el demo está en __main__; reinvocamos
            import review_cli
            sys.argv = ["review_cli.py", "--demo"]
            review_cli.__name__ = "__main__"
            exec(open(review_cli.__file__).read(), review_cli.__dict__)
        else:
            cli.run()
        return 0

    # Pipeline
    sheet_dry_run = not args.sheet_real
    use_real = args.no_mock
    pipeline = RadarPipeline(
        use_real_sources=use_real,
        sheet_dry_run=sheet_dry_run,
    )
    result = pipeline.run()
    pipeline.print_summary(result)

    print(f"\n  Outputs generados en: /home/z/my-project/download/sample_data/")
    print(f"    - signals_mock.jsonl     ({result.signals_collected} señales)")
    print(f"    - cases.jsonl            ({len(result.cases)} casos)")
    print(f"    - review_queue.csv       ({result.cases_canonical} pendientes)")
    print(f"    - audit_trail.log        ({result.audit_entries} entradas)")
    print(f"    - evidence/              ({result.cases_canonical} carpetas)")
    print(f"\n  Para revisar casos: python main.py --review")
    print(f"  Para demo automática: python main.py --review --demo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
