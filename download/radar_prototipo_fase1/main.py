"""
main.py — Entry point del Radar de Oportunidades (Fase 1).

Uso:
    python main.py                          # pipeline end-to-end con mock data
    python main.py --review                 # CLI de revisión
    python main.py --review --demo          # demo automática
    python main.py --sheet-write            # subir vía gspread + service account
    python main.py --sheet-write --dry-run  # serializar filas sin tocar Google
    python main.py --sheet-push-webhook     # subir vía POST a Apps Script Web App
    python main.py --help

Requisitos:
    Python 3.10+
    Sólo stdlib para Fase 1 (gspread opcional para --sheet-write)
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

from pipeline import RadarPipeline
from review_cli import ReviewCLI
from storage import load_cases_jsonl, AuditTrail
from sheets_uploader import GoogleSheetsUploader, MissingCredentialsError
from webhook_uploader import WebhookUploader, MissingWebhookURLError
import config


def cmd_sheet_write(dry_run: bool) -> int:
    """
    Sube los casos canónicos de cases.jsonl a Google Sheets.

    Comportamiento:
        - Si dry_run=True: imprime las filas serializadas y NO toca Google.
        - Si dry_run=False: requiere RADAR_GOOGLE_SERVICE_ACCOUNT_FILE apuntando
          a un archivo existente. Si falta, lanza MissingCredentialsError con
          mensaje "Missing credentials file ...".
        - Sin modo mock ni dry-run implícito.
    """
    cases_data = load_cases_jsonl()
    if not cases_data:
        print("No hay casos en cases.jsonl. Ejecutá `python main.py` primero.")
        return 1

    # Filtrar sólo canónicos
    from models import Case
    cases = [Case(**c) for c in cases_data if c.get("is_canonical")]
    print(f"Casos canónicos a subir: {len(cases)}")

    if dry_run:
        print("\n--- DRY-RUN: filas que se subirían (NO se toca Google) ---\n")
        for c in cases:
            row = c.to_sheet_row()
            print(json.dumps(row, ensure_ascii=False, indent=2))
            print("---")
        print(f"\nTotal: {len(cases)} filas. Para subida real, correr sin --dry-run.")
        return 0

    # Modo real: el constructor falla si faltan credenciales
    audit = AuditTrail()
    try:
        uploader = GoogleSheetsUploader(audit=audit)
    except MissingCredentialsError as e:
        print(f"✗ {e}", file=sys.stderr)
        print(
            "  Setear env var: export RADAR_GOOGLE_SERVICE_ACCOUNT_FILE=/path/local/service-account.json",
            file=sys.stderr,
        )
        return 2

    print(f"  Credenciales: {uploader.credentials_path}")
    print(f"  Spreadsheet:  {uploader.spreadsheet_id}")
    print(f"  Worksheet:    {uploader.worksheet_name}")
    print()

    summary = uploader.append_rows(cases)
    print("\n" + "=" * 70)
    print("  RESULTADO DE SUBIDA (gspread)")
    print("=" * 70)
    print(f"  Total casos:   {summary['total']}")
    print(f"  Appended:      {summary['appended']}")
    print(f"  Updated:       {summary['updated']}")
    print(f"  Skipped:       {summary['skipped']}")
    print(f"  Errors:        {len(summary['errors'])}")
    if summary["errors"]:
        print("\n  ERRORES:")
        for err in summary["errors"]:
            print(f"    - {err['case_id']}: {err['error']}")
    print(f"\n  Sheet URL:     https://docs.google.com/spreadsheets/d/{uploader.spreadsheet_id}/edit")
    print("=" * 70)
    return 0 if not summary["errors"] else 3


def cmd_sheet_push_webhook(dry_run: bool) -> int:
    """
    Sube los casos canónicos a Google Sheets vía Apps Script Web App (HTTP POST).

    Comportamiento:
        - Si dry_run=True: imprime el payload JSON y NO hace HTTP.
        - Si dry_run=False: requiere RADAR_WEBHOOK_URL seteada. Si falta,
          lanza MissingWebhookURLError con mensaje "Missing webhook URL".
        - Sin modo mock ni dry-run implícito.
        - Sólo stdlib (urllib), no requiere gspread ni service account.
    """
    cases_data = load_cases_jsonl()
    if not cases_data:
        print("No hay casos en cases.jsonl. Ejecutá `python main.py` primero.")
        return 1

    from models import Case
    cases = [Case(**c) for c in cases_data if c.get("is_canonical")]
    print(f"Casos canónicos a pushear: {len(cases)}")

    if dry_run:
        print("\n--- DRY-RUN: payload que se enviaría (NO se hace HTTP) ---\n")
        # Usar static method para no requerir URL (dry-run puro)
        from webhook_uploader import WebhookUploader
        payload = {"cases": [WebhookUploader.case_to_payload(c) for c in cases]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"\nTotal: {len(cases)} casos. Para push real, correr sin --dry-run.")
        print(f"Requiere: export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<ID>/exec")
        return 0

    audit = AuditTrail()
    try:
        uploader = WebhookUploader(audit=audit)
    except MissingWebhookURLError as e:
        print(f"✗ {e}", file=sys.stderr)
        print(
            "  Setear env var: export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<DEPLOY_ID>/exec",
            file=sys.stderr,
        )
        return 2

    print(f"  Webhook URL:   {uploader.webhook_url}")
    print(f"  Timeout:       {uploader.timeout}s")
    print()

    summary = uploader.push(cases)
    print("\n" + "=" * 70)
    print("  RESULTADO DE PUSH (webhook)")
    print("=" * 70)
    print(f"  Total casos:   {summary['total']}")
    print(f"  Pushed:        {summary['pushed']}")
    print(f"  Response:      {summary['response']!r}")
    print(f"  Errors:        {len(summary['errors'])}")
    if summary["errors"]:
        print("\n  ERRORES:")
        for err in summary["errors"]:
            print(f"    - {err.get('error', err)}")
    print(f"\n  Sheet URL:     https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID}/edit")
    print("=" * 70)
    return 0 if not summary["errors"] else 3


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
        "--sheet-write", action="store_true",
        help="Sube casos canónicos a Google Sheet vía gspread (requiere RADAR_GOOGLE_SERVICE_ACCOUNT_FILE)",
    )
    parser.add_argument(
        "--sheet-push-webhook", action="store_true",
        help="Sube casos vía POST a Apps Script Web App (requiere RADAR_WEBHOOK_URL)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Con --sheet-write o --sheet-push-webhook: no toca Google, sólo serializa",
    )
    parser.add_argument(
        "--no-mock", action="store_true",
        help="Usa fuentes reales en vez de mock (Fase 2/3, requiere conectores implementados)",
    )
    args = parser.parse_args()

    if args.review:
        cli = ReviewCLI()
        if args.demo:
            import review_cli
            sys.argv = ["review_cli.py", "--demo"]
            review_cli.__name__ = "__main__"
            exec(open(review_cli.__file__).read(), review_cli.__dict__)
        else:
            cli.run()
        return 0

    if args.sheet_write:
        return cmd_sheet_write(dry_run=args.dry_run)

    if args.sheet_push_webhook:
        return cmd_sheet_push_webhook(dry_run=args.dry_run)

    # Pipeline end-to-end (sin tocar Google)
    use_real = args.no_mock
    pipeline = RadarPipeline(use_real_sources=use_real, sheet_dry_run=True)
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
    print(f"  Para subir a Sheet (gspread):    python main.py --sheet-write")
    print(f"    (requiere RADAR_GOOGLE_SERVICE_ACCOUNT_FILE)")
    print(f"  Para subir a Sheet (webhook):    python main.py --sheet-push-webhook")
    print(f"    (requiere RADAR_WEBHOOK_URL)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
