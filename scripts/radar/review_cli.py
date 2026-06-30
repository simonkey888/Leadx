"""
review_cli.py — CLI interactivo para revisión humana de casos.

Comandos:
  list                  Lista casos pendientes (status=needs_review) con SLA
  show <case_id>        Muestra detalle completo de un caso
  approve <id> [notas]  Aprueba un caso para acción comercial
  reject <id> [notas]   Rechaza un caso
  duplicate <id> [notas] Marca como duplicado
  needs_more <id> [notas] Marca como necesita más datos
  stats                 Estadísticas de la cola
  audit [N]             Muestra últimas N entradas del audit trail
  verify                Verifica integridad de la cadena de audit trail
  quit / exit           Salir

SLA: 24h desde created_at. Casos vencidos se marcan con [SLA VENCIDO].
"""
from __future__ import annotations
import sys
import json
from typing import List, Optional

from models import Case, ReviewAction, now_iso
import config
from storage import (
    AuditTrail, ReviewQueue, EvidenceStore,
    load_cases_jsonl,
)


class ReviewCLI:
    def __init__(self):
        self.audit = AuditTrail()
        self.queue = ReviewQueue()
        self.evidence = EvidenceStore()
        self.cases_by_id = {c["case_id"]: c for c in load_cases_jsonl()}

    def cmd_list(self) -> None:
        pending = self.queue.pending()
        if not pending:
            print("No hay casos pendientes de revisión.")
            return
        print(f"\n{'case_id':14s} {'score':5s} {'band':8s} {'juris':12s} {'problem':15s} {'source':25s} {'SLA':>10s}")
        print("-" * 95)
        for row in pending:
            sla = float(row["sla_hours_remaining"]) if row["sla_hours_remaining"] else 0
            sla_str = f"{sla:.1f}h"
            marker = " ⚠" if sla < 0 else ""
            print(f"{row['case_id']:14s} {row['score']:5s} {row['score_band']:8s} "
                  f"{row['jurisdiction']:12s} {row['problem_type']:15s} "
                  f"{row['source_id']:25s} {sla_str:>10s}{marker}")
        print()

    def cmd_show(self, case_id: str) -> None:
        case = self.cases_by_id.get(case_id)
        if not case:
            print(f"Caso no encontrado: {case_id}")
            return
        print("\n" + "=" * 70)
        print(f"  CASO {case['case_id']}")
        print("=" * 70)
        print(f"  Score:           {case['score']} ({case['score_band']})")
        print(f"  Status:          {case['status']}")
        print(f"  Source:          {case['source_id']}")
        print(f"  Source URL:      {case['source_url']}")
        print(f"  Profile URL:     {case['profile_url'] or '—'}")
        print(f"  Author:          {case['name_or_alias']}")
        print(f"  Timestamp:       {case['timestamp']}")
        print(f"  Jurisdicción:    {case['jurisdiction'] or '—'}")
        print(f"  Localidad:       {case['locality'] or '—'}")
        print(f"  Problema:        {case['problem_type']}")
        print(f"  Vehículo:        {case['vehicle_type'] or '—'}")
        print(f"  Patente:         {case['patent'] or '—'}")
        print(f"  Año:             {case['year'] or '—'}")
        print(f"  Monto:           {case['amount'] or '—'}")
        print(f"  Score breakdown: {case['score_breakdown']}")
        print(f"  Duplicado de:    {case.get('duplicate_of') or '—'}")
        print(f"  Duplicados:      {case.get('duplicates') or []}")
        print(f"  Evidence path:   {case.get('evidence_path') or '—'}")
        print(f"  Evidence SHA256: {case.get('evidence_sha256') or '—'}")
        print("-" * 70)
        print("  EVIDENCIA TEXTUAL:")
        print("-" * 70)
        print(f"  {case['evidence_text']}")
        print("-" * 70)
        if case.get('reviewed_by'):
            print(f"  Revisado por:    {case['reviewed_by']}")
            print(f"  Acción:          {case['review_action']}")
            print(f"  Fecha:           {case['reviewed_at']}")
            print(f"  Notas:           {case['review_notes']}")
        print("=" * 70 + "\n")

    def cmd_review(self, action: str, case_id: str, notes: str = "") -> None:
        case = self.cases_by_id.get(case_id)
        if not case:
            print(f"Caso no encontrado: {case_id}")
            return
        # Reconstruir Case mínimo para queue.apply_review
        c = Case(**case)
        reviewer = "operator_cli"
        ra = ReviewAction(case_id=case_id, action=action, reviewer=reviewer, notes=notes)
        try:
            self.queue.apply_review(c, ra, self.audit)
            # Actualizar dict local
            self.cases_by_id[case_id] = c.to_dict()
            print(f"✓ Caso {case_id} → {action} por {reviewer}")
            print(f"  Audit trail actualizado.")
        except ValueError as e:
            print(f"✗ {e}")

    def cmd_stats(self) -> None:
        stats = self.queue.stats()
        print("\nEstadísticas de la cola de revisión:")
        print("-" * 40)
        for status, count in sorted(stats.items()):
            print(f"  {status:25s} {count:5d}")
        print("-" * 40)
        total = sum(stats.values())
        print(f"  {'TOTAL':25s} {total:5d}\n")

    def cmd_audit(self, n: int = 10) -> None:
        entries = self.audit.read_all()[-n:]
        print(f"\nÚltimas {len(entries)} entradas del audit trail:")
        print("-" * 100)
        for e in entries:
            details_str = json.dumps(e["details"], ensure_ascii=False)
            if len(details_str) > 80:
                details_str = details_str[:77] + "…"
            print(f"  {e['timestamp'][:19]} | {e['actor']:20s} | {e['action']:18s} | "
                  f"{e['entity_type']:8s} | {e['entity_id']:20s} | {details_str}")
        print("-" * 100)
        print(f"  Cadena íntegra: {'✓' if self.audit.verify_chain() else '✗ ROTA'}\n")

    def cmd_verify(self) -> None:
        ok = self.audit.verify_chain()
        print(f"\nCadena de audit trail: {'✓ ÍNTEGRA' if ok else '✗ ROTA'}\n")

    def run(self) -> None:
        print("=" * 70)
        print("  RADAR DE OPORTUNIDADES — CLI de Revisión Humana (Fase 1)")
        print("=" * 70)
        print("  Comandos: list | show <id> | approve <id> [notas] | reject <id> [notas]")
        print("            duplicate <id> [notas] | needs_more <id> [notas]")
        print("            stats | audit [N] | verify | quit")
        print("=" * 70 + "\n")

        while True:
            try:
                line = input("radar> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nChau.")
                break
            if not line:
                continue
            parts = line.split(maxsplit=2)
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("quit", "exit", "q"):
                print("Chau.")
                break
            elif cmd == "list":
                self.cmd_list()
            elif cmd == "show" and args:
                self.cmd_show(args[0])
            elif cmd == "stats":
                self.cmd_stats()
            elif cmd == "audit":
                n = int(args[0]) if args else 10
                self.cmd_audit(n)
            elif cmd == "verify":
                self.cmd_verify()
            elif cmd in ("approve", "reject", "duplicate", "needs_more") and args:
                notes = args[1] if len(args) > 1 else ""
                action_map = {"needs_more": "needs_more_data"}
                action = action_map.get(cmd, cmd)
                self.cmd_review(action, args[0], notes)
            else:
                print(f"Comando inválido: {line}")
                print("Comandos: list | show <id> | approve <id> | reject <id> | duplicate <id> | needs_more <id> | stats | audit | verify | quit")


if __name__ == "__main__":
    cli = ReviewCLI()
    # Si se pasa --non-interactive, ejecuta demo automática
    if "--demo" in sys.argv:
        print("\n--- DEMO AUTOMÁTICA ---\n")
        cli.cmd_stats()
        cli.cmd_list()
        if cli.cases_by_id:
            first_id = list(cli.cases_by_id.keys())[0]
            cli.cmd_show(first_id)
            cli.cmd_review("approve", first_id, "Caso válido para contacto manual.")
            cli.cmd_stats()
            cli.cmd_audit(5)
            cli.cmd_verify()
    else:
        cli.run()
