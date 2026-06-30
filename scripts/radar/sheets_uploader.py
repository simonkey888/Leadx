"""
sheets_uploader.py — Contrato de subida a Google Sheets (SPEC-ONLY).

ESTE MÓDULO ES SPEC-ONLY:
- Define el contrato de entrada y la lógica de escritura.
- NO ejecuta llamadas reales a Google Sheets en este entorno.
- Si la variable de entorno RADAR_GOOGLE_SERVICE_ACCOUNT_FILE no apunta a un
  archivo existente, lanza RuntimeError("Missing credentials file").
- No hay modo mock ni dry-run implícito. El dry-run explícito (--dry-run en CLI)
  serializa las filas a stdout sin tocar la API.

Contrato de entrada:
    RADAR_GOOGLE_SERVICE_ACCOUNT_FILE=/path/local/service-account.json

Operación soportada:
    {
      "operation": "append_rows",
      "target": "google_sheets",
      "spreadsheet_id": "1jLeM6k_Q10JBNFSn46TCoz7dgVdnOS79lyIPO283xE0",
      "worksheet": "cases",
      "rows": [<Case.to_sheet_row()>...],
      "requires_runtime_execution": true
    }

Reglas (glm_instruction_block):
    1. NEVER store private keys inside code
    2. ONLY use service account via file path env var
    3. ONLY append rows, never overwrite full sheet
    4. ALWAYS log case_id after write
    5. DO NOT create duplicates if case_id exists
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote

import config
from models import Case
from storage import AuditTrail


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------
class MissingCredentialsError(RuntimeError):
    """Raised when RADAR_GOOGLE_SERVICE_ACCOUNT_FILE is empty or file missing."""
    pass


class SheetSchemaError(RuntimeError):
    """Raised when the worksheet headers don't match SHEET_HEADERS and can't be merged."""
    pass


class SheetWriteError(RuntimeError):
    """Raised when a write attempt fails after retry."""
    pass


# ---------------------------------------------------------------------------
# Uploader
# ---------------------------------------------------------------------------
class GoogleSheetsUploader:
    """
    Sube casos a Google Sheets en modo append_only con dedup por case_id.

    Contract:
        - input: RADAR_GOOGLE_SERVICE_ACCOUNT_FILE (env var, string path)
        - behavior: if path missing → raise MissingCredentialsError
                    ("Missing credentials file")
        - no mocks, no dry-run implicit
        - real Google Sheets calls happen only when methods are invoked at runtime
          in an environment that has the credentials file
    """

    def __init__(
        self,
        spreadsheet_id: str = config.GOOGLE_SHEET_ID,
        worksheet_name: str = config.GOOGLE_SHEET_TAB,
        credentials_path: Optional[str] = None,
        audit: Optional[AuditTrail] = None,
    ):
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet_name
        self.audit = audit

        # Resolución del path de credenciales (env var es la fuente única)
        cred_path = credentials_path or os.environ.get(
            "RADAR_GOOGLE_SERVICE_ACCOUNT_FILE", ""
        )

        if not cred_path:
            raise MissingCredentialsError(
                "Missing credentials file "
                "(env var RADAR_GOOGLE_SERVICE_ACCOUNT_FILE is empty)"
            )
        if not Path(cred_path).is_file():
            raise MissingCredentialsError(
                f"Missing credentials file (path does not exist: {cred_path})"
            )

        self.credentials_path = cred_path
        self._client = None
        self._sheet = None
        self._worksheet = None

    # ------------------------------------------------------------------
    # Conexión (lazy) — sólo se invoca en runtime real
    # ------------------------------------------------------------------
    def _connect(self):
        """
        Autentica con Google via gspread.service_account().
        Requiere gspread instalado. No cachea el client hasta primera llamada exitosa.
        """
        if self._client is not None:
            return
        try:
            import gspread  # type: ignore
        except ImportError as e:
            raise SheetWriteError(
                "gspread no instalado. Instalar con: pip install gspread"
            ) from e

        self._client = gspread.service_account(filename=self.credentials_path)
        self._sheet = self._client.open_by_key(self.spreadsheet_id)

        # Asegurar que el worksheet exista
        try:
            self._worksheet = self._sheet.worksheet(self.worksheet_name)
        except Exception:
            # Si no existe, lo crea
            self._worksheet = self._sheet.add_worksheet(
                title=self.worksheet_name, rows=1000, cols=len(config.SHEET_HEADERS)
            )

    # ------------------------------------------------------------------
    # Headers: ensure_headers_then_ready_to_write
    # ------------------------------------------------------------------
    def ensure_headers(self) -> Dict[str, Any]:
        """
        Asegura que la fila 1 del worksheet tenga los headers de SHEET_HEADERS.

        Política (config.SHEET_HEADER_POLICY):
            - if_empty_sheet: create_headers
            - if_headers_exist: validate_and_merge_if_missing
            - never_overwrite_row_1: True

        Returns:
            Dict con: action ('created'|'validated'|'merged'),
                      missing_headers, headers_present
        """
        self._connect()
        # Leer primera fila
        first_row = self._worksheet.row_values(1) if self._worksheet.row_count > 0 else []

        if not first_row:
            # Hoja vacía: crear headers
            self._worksheet.update([config.SHEET_HEADERS])
            self._log_audit("sheet_ensure_headers", "created",
                             details={"headers": config.SHEET_HEADERS})
            return {"action": "created", "missing_headers": [], "headers_present": config.SHEET_HEADERS}

        # Validar / merge
        present = [h.strip() for h in first_row]
        required = list(config.SHEET_HEADERS)
        missing = [h for h in required if h not in present]

        if not missing:
            self._log_audit("sheet_ensure_headers", "validated",
                             details={"headers": present})
            return {"action": "validated", "missing_headers": [], "headers_present": present}

        # Merge: agregar columnas faltantes al final de la fila 1
        # (nunca sobrescribir row_1 existente)
        new_headers = present + missing
        # Pad para que tenga la misma longitud que las filas nuevas
        self._worksheet.update([new_headers])
        self._log_audit("sheet_ensure_headers", "merged",
                         details={"added": missing, "final_headers": new_headers})
        return {"action": "merged", "missing_headers": missing, "headers_present": new_headers}

    # ------------------------------------------------------------------
    # Dedup lookup
    # ------------------------------------------------------------------
    def _find_case_row(self, case_id: str) -> Optional[int]:
        """
        Busca el número de fila (1-indexed) de un case_id existente.
        Returns None si no existe.
        """
        self._connect()
        try:
            cell = self._worksheet.find(case_id, in_column=1)
            return cell.row if cell else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Append or update
    # ------------------------------------------------------------------
    def append_or_update(self, case: Case) -> Dict[str, Any]:
        """
        Pipeline por caso:
            validate_case_schema → normalize_fields → deduplicate_by_case_id
            → compute_priority_level → generate_whatsapp_link
            → append_to_sheet (o update_score_if_higher) → log_audit_trail

        Estrategia dedup (config.SHEET_DUPLICATE_STRATEGY):
            'update_score_if_higher' → si el case_id existe y el nuevo score
            es mayor, actualiza la fila; sino, no hace nada.

        Returns:
            Dict con: case_id, action ('appended'|'updated'|'skipped_lower_score'),
                      row, score
        """
        # 1. validate_case_schema
        row = case.to_sheet_row()
        missing_fields = [k for k in config.SHEET_HEADERS if k not in row]
        if missing_fields:
            raise SheetSchemaError(
                f"Case {case.case_id} missing required fields: {missing_fields}"
            )

        # 2-4. normalize + priority_level ya resueltos en to_sheet_row()
        # 5. generate_whatsapp_link ya resuelto en to_sheet_row()

        # 6. deduplicate_by_case_id
        existing_row = self._find_case_row(case.case_id)

        if existing_row is None:
            # 6a. append_to_sheet
            self._write_with_retry([row], append=True)
            self._log_audit("sheet_write", "appended",
                             entity_id=case.case_id,
                             details={"row": row, "score": case.score})
            return {
                "case_id": case.case_id,
                "action": "appended",
                "score": case.score,
            }

        # 6b. update_score_if_higher
        existing_values = self._worksheet.row_values(existing_row)
        # Buscar columna 'score'
        headers = self._worksheet.row_values(1)
        try:
            score_col_idx = headers.index("score")
            existing_score = int(existing_values[score_col_idx]) if score_col_idx < len(existing_values) else 0
        except (ValueError, IndexError):
            existing_score = 0

        if case.score > existing_score:
            # Update completo de la fila (preserva el case_id, actualiza el resto)
            self._update_row(existing_row, row)
            self._log_audit("sheet_write", "updated_higher_score",
                             entity_id=case.case_id,
                             details={
                                 "old_score": existing_score,
                                 "new_score": case.score,
                                 "row": existing_row,
                             })
            return {
                "case_id": case.case_id,
                "action": "updated",
                "old_score": existing_score,
                "new_score": case.score,
                "row": existing_row,
            }

        # Skip (no crear duplicado, no actualizar)
        self._log_audit("sheet_write", "skipped_lower_score",
                         entity_id=case.case_id,
                         details={
                             "existing_score": existing_score,
                             "new_score": case.score,
                             "row": existing_row,
                         })
        return {
            "case_id": case.case_id,
            "action": "skipped_lower_score",
            "existing_score": existing_score,
            "new_score": case.score,
            "row": existing_row,
        }

    # ------------------------------------------------------------------
    # Batch append
    # ------------------------------------------------------------------
    def append_rows(self, cases: List[Case]) -> Dict[str, Any]:
        """
        Operación batch: para cada caso, ejecuta append_or_update.

        Returns:
            Dict con: total, appended, updated, skipped, errors
        """
        # Asegurar headers primero
        headers_result = self.ensure_headers()

        appended = 0
        updated = 0
        skipped = 0
        errors: List[Dict[str, Any]] = []

        for case in cases:
            try:
                result = self.append_or_update(case)
                action = result["action"]
                if action == "appended":
                    appended += 1
                elif action == "updated":
                    updated += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append({"case_id": case.case_id, "error": str(e)})
                self._log_audit("sheet_write", "error",
                                 entity_id=case.case_id,
                                 details={"error": str(e)})

        summary = {
            "operation": "append_rows",
            "target": "google_sheets",
            "spreadsheet_id": self.spreadsheet_id,
            "worksheet": self.worksheet_name,
            "total": len(cases),
            "appended": appended,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "headers_action": headers_result["action"],
            "requires_runtime_execution": True,
        }
        self._log_audit("sheet_batch", "completed",
                         entity_id="batch",
                         details=summary)
        return summary

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------
    def _write_with_retry(self, rows: List[Dict[str, Any]], append: bool = True) -> None:
        """
        Escribe filas con retry_once_then_log_error (config.SHEET_ON_FAILURE).
        """
        last_exc: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                self._connect()
                values = [[r.get(h, "") for h in config.SHEET_HEADERS] for r in rows]
                if append:
                    self._worksheet.append_rows(values, value_input_option="USER_ENTERED")
                else:
                    # update_row se maneja en _update_row
                    pass
                return
            except Exception as e:
                last_exc = e
                if attempt == 1:
                    time.sleep(0.5)  # backoff corto antes del retry
                    continue
                # Agotado el retry
                raise SheetWriteError(
                    f"Sheet write failed after retry: {e}"
                ) from e
        # No debería llegar aquí
        raise SheetWriteError(f"Sheet write failed: {last_exc}")

    def _update_row(self, row_num: int, row: Dict[str, Any]) -> None:
        """Actualiza una fila existente con los valores nuevos."""
        last_exc: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                self._connect()
                values = [[row.get(h, "") for h in config.SHEET_HEADERS]]
                # Range: A{row}:{last_col}{row}
                last_col_letter = chr(ord('A') + len(config.SHEET_HEADERS) - 1)
                cell_range = f"A{row_num}:{last_col_letter}{row_num}"
                self._worksheet.update(cell_range, values, value_input_option="USER_ENTERED")
                return
            except Exception as e:
                last_exc = e
                if attempt == 1:
                    time.sleep(0.5)
                    continue
                raise SheetWriteError(
                    f"Sheet update failed after retry: {e}"
                ) from e
        raise SheetWriteError(f"Sheet update failed: {last_exc}")

    def _log_audit(
        self,
        action: str,
        result: str,
        entity_type: str = "case",
        entity_id: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.audit is None:
            return
        self.audit.append(
            actor="system:sheets_uploader",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details={"result": result, **(details or {})},
        )


# ---------------------------------------------------------------------------
# Helper standalone para construir WhatsApp link (uso opcional)
# ---------------------------------------------------------------------------
def build_whatsapp_link(whatsapp_number: str, message: Optional[str] = None) -> str:
    """
    Construye un link de WhatsApp según el spec del uploader.

    Formato: https://wa.me/{whatsapp_number}?text={encoded_message}
    Si no hay número, devuelve string vacío.
    """
    if not whatsapp_number:
        return ""
    msg = message or config.WHATSAPP_DEFAULT_MESSAGE
    encoded = quote(msg)
    # Normalizar número: sólo dígitos (sacar +, espacios, guiones)
    normalized = "".join(c for c in whatsapp_number if c.isdigit())
    return f"https://wa.me/{normalized}?text={encoded}"


# ---------------------------------------------------------------------------
# Smoke test (spec-only): verifica el contrato de error, NO llama a Google
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST sheets_uploader.py (SPEC-ONLY, no llama a Google)")
    print("=" * 70)

    # 1. Sin env var → Missing credentials file
    saved = os.environ.pop("RADAR_GOOGLE_SERVICE_ACCOUNT_FILE", None)
    try:
        try:
            uploader = GoogleSheetsUploader()
            print(f"  ✗ FAIL: debería haber lanzado MissingCredentialsError")
            sys.exit(1)
        except MissingCredentialsError as e:
            assert "Missing credentials file" in str(e), f"Mensaje incorrecto: {e}"
            print(f"  ✓ Sin credenciales → '{e}'")
    finally:
        if saved is not None:
            os.environ["RADAR_GOOGLE_SERVICE_ACCOUNT_FILE"] = saved

    # 2. Con path inexistente → Missing credentials file
    os.environ["RADAR_GOOGLE_SERVICE_ACCOUNT_FILE"] = "/tmp/no-existe-12345.json"
    try:
        try:
            uploader = GoogleSheetsUploader()
            print(f"  ✗ FAIL: debería haber lanzado MissingCredentialsError")
            sys.exit(1)
        except MissingCredentialsError as e:
            assert "Missing credentials file" in str(e), f"Mensaje incorrecto: {e}"
            print(f"  ✓ Path inexistente → '{e}'")
    finally:
        os.environ.pop("RADAR_GOOGLE_SERVICE_ACCOUNT_FILE", None)
        if saved is not None:
            os.environ["RADAR_GOOGLE_SERVICE_ACCOUNT_FILE"] = saved

    # 3. build_whatsapp_link standalone
    link = build_whatsapp_link("+54 11 5555-1234")
    expected = "https://wa.me/541155551234?text=Hola%2C%20vi%20tu%20consulta%20sobre%20multas.%20Te%20puedo%20ayudar%20a%20revisarlo."
    assert link == expected, f"WhatsApp link incorrecto:\n  got:      {link}\n  expected: {expected}"
    print(f"  ✓ build_whatsapp_link → {link}")

    # 4. Schema de headers (sin tocar Google)
    print(f"  ✓ SHEET_HEADERS ({len(config.SHEET_HEADERS)} cols): {', '.join(config.SHEET_HEADERS[:5])}…")

    # 5. to_sheet_row genera fila con EXACTAMENTE las columnas del schema
    from models import Case
    from storage import AuditTrail
    case = Case(
        case_id="case-test",
        signal_id="sig-test",
        source_id="facebook_public_groups",
        source_url="https://example.com/post/abc",
        profile_url="https://example.com/user/1",
        timestamp="2026-06-30T10:00:00-03:00",
        name_or_alias="Test User",
        vehicle_type="auto",
        patent="ABC123",
        jurisdiction="CABA",
        locality="Caballito",
        problem_type="fotomulta",
        year=2020,
        amount=18500.0,
        evidence_text="Test evidence text",
        score=82,
        score_band="critical",
        whatsapp_number="541155551234",
    )
    row = case.to_sheet_row()
    assert list(row.keys()) == config.SHEET_HEADERS, \
        f"Schema mismatch: {list(row.keys())} vs {config.SHEET_HEADERS}"
    assert row["whatsapp_link"].startswith("https://wa.me/541155551234?text="), \
        f"WhatsApp link no generado: {row['whatsapp_link']}"
    assert row["priority_level"] == "critical"
    assert row["review_state"] == "needs_review"
    print(f"  ✓ to_sheet_row genera fila con schema exacto ({len(row)} cols)")
    print(f"  ✓ whatsapp_link generado: {row['whatsapp_link'][:60]}…")
    print(f"  ✓ priority_level={row['priority_level']} | review_state={row['review_state']}")

    print("\n" + "=" * 70)
    print("  ✓ Contrato spec-only verificado. No se ejecutaron llamadas a Google.")
    print("=" * 70)
    print("""
  Para ejecutar subida real (en máquina del operador con credenciales):

      export RADAR_GOOGLE_SERVICE_ACCOUNT_FILE=/path/local/service-account.json
      pip install gspread
      python main.py --sheet-write

  Si el archivo no existe, el uploader lanza:
      Missing credentials file (path does not exist: /path/local/service-account.json)
""")
