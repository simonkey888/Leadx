"""
generate_report.py — Genera reporte CRM legible a partir de radar_v4_output.json.

El JSON es para máquinas. Este reporte es para personas comerciales:
responde en 10 segundos: ¿quién tiene el problema? ¿cómo lo contacto? ¿vale la pena?
"""
import json
import sys
from pathlib import Path
from datetime import datetime

OUTPUT_PATH = Path("/home/z/my-project/download/radar_v4_reporte.md")
OUTPUT_TXT_PATH = Path("/home/z/my-project/download/radar_v4_reporte.txt")


def stars(score: int) -> str:
    """Mapea urgency 0-100 a 5 estrellas."""
    if score >= 80:
        return "⭐⭐⭐⭐⭐"
    elif score >= 60:
        return "⭐⭐⭐⭐☆"
    elif score >= 40:
        return "⭐⭐⭐☆☆"
    elif score >= 20:
        return "⭐⭐☆☆☆"
    return "⭐☆☆☆☆"


def confidence_pct(score: int) -> str:
    return f"{score}%"


def problem_short(lead: dict) -> str:
    """Resume el problema en 1 línea clara."""
    reasons = {
        "declara_multas": "Tiene multas/fotomultas",
        "declara_problema_transferencia": "Problema con transferencia",
        "declara_problema_libre_deuda": "Necesita libre deuda",
        "consulta_documentacion": "Consulta sobre trámite",
        "vende_auto_titular": "Vende vehículo (titular)",
        "vende_auto": "Vende vehículo",
        "permuta_auto": "Permuta vehículo",
        "generico": "Lead vehicular genérico",
    }
    base = reasons.get(lead.get("lead_reason", ""), "Lead vehicular")

    # Sumar dolor del quote si está disponible
    qt = lead.get("quoted_text", "").lower()
    if "no es mi auto" in qt or "nisiquiera es" in qt:
        return "Multa que no es suya (error de patente)"
    if "libre deuda falso" in qt:
        return "Compró auto con libre deuda falso"
    if "no me entregó" in qt or "nunca te entregó" in qt:
        return "Vendedor no entregó formulario 08"
    if "multas vencidas sin notificar" in qt:
        return "Multas vencidas sin notificación"
    if "radicado en otra" in qt:
        return "Auto radicado en otra provincia"
    if "con multas impagas" in qt:
        return "Transferencia con multas impagas"
    if "desvinculacion de multas" in qt:
        return "Quiere desvincular multas del vehículo"
    if "par d multas" in qt:
        return "Vender moto con multas"
    if "no me deja transferir" in qt:
        return "No le dejan transferir"
    if "me llegó" in qt and "multa" in qt:
        return "Le llegó multa"
    return base


def vehicle_display(lead: dict) -> str:
    v = lead.get("vehicle_if_detected", "")
    return v.title() if v else "No mencionado"


def city_display(lead: dict) -> str:
    c = lead.get("city_if_detected", "")
    return c if c else "No detectada"


def province_display(lead: dict) -> str:
    p = lead.get("province_if_detected", "")
    return p if p else "No detectada"


def platform_display(lead: dict) -> str:
    p = lead.get("platform", "")
    mapping = {
        "facebook.com": "Facebook",
        "reddit.com": "Reddit",
        "twitter.com": "X (Twitter)",
        "x.com": "X (Twitter)",
        "taringa.net": "Taringa",
    }
    return mapping.get(p, p.title() if p else "Desconocida")


def date_display(lead: dict) -> str:
    d = lead.get("date", "")
    if not d:
        return "No disponible"
    # Intentar formatear
    try:
        if "T" in d:
            dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        return d[:10]
    except Exception:
        return d


def contact_display(lead: dict, field: str) -> str:
    val = lead.get(field, "")
    return val if val else "No encontrado públicamente."


def person_display(lead: dict) -> str:
    name = lead.get("person_name", "")
    if not name or name == "(sin nombre)":
        return "Anónimo (no publicado)"
    return name


def quote_clean(lead: dict, max_len: int = 200) -> str:
    qt = lead.get("quoted_text", "")
    if not qt:
        return ""
    # Limpiar el quote: sacar el nombre del sitio al inicio si está repetido
    if " - " in qt[:80]:
        # Ej: "Hola buenas... - Facebook. Hola buenas..."
        # tomar la parte después del " - "
        parts = qt.split(" - ", 1)
        if len(parts) > 1:
            qt = parts[1]
    # Truncar
    if len(qt) > max_len:
        qt = qt[:max_len - 1] + "…"
    return qt


def generate_report():
    with open("/home/z/my-project/download/radar_v4_output.json") as f:
        data = json.load(f)

    real_leads = data.get("real_leads", [])
    commercial_signals = data.get("commercial_signals", [])

    lines_md = []
    lines_txt = []

    # Header
    lines_md.append("# 🔍 RADAR DE OPORTUNIDADES — Reporte Comercial")
    lines_md.append("")
    lines_md.append(f"**Generado:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    lines_md.append(f"**Misión:** Encontrar personas con problemas vehiculares reales")
    lines_md.append("")
    lines_md.append("---")
    lines_md.append("")

    # Versión texto plano del header
    lines_txt.append("=" * 70)
    lines_txt.append("  RADAR DE OPORTUNIDADES - REPORTE COMERCIAL")
    lines_txt.append("=" * 70)
    lines_txt.append("")
    lines_txt.append(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    lines_txt.append("")

    # ===== SECCIÓN 1: LEADS CALIENTES =====
    lines_md.append("## 🔥 LEADS CALIENTES (Dolor explícito)")
    lines_md.append("")
    lines_md.append(f"_{len(real_leads)} personas declarando un problema real con multas, transferencia o libre deuda._")
    lines_md.append("")

    lines_txt.append("-" * 70)
    lines_txt.append("  LEADS CALIENTES (Dolor explicito)")
    lines_txt.append("-" * 70)
    lines_txt.append(f"  {len(real_leads)} personas declarando un problema real.")
    lines_txt.append("")

    for i, lead in enumerate(real_leads, 1):
        problem = problem_short(lead)
        person = person_display(lead)
        province = province_display(lead)
        city = city_display(lead)
        vehicle = vehicle_display(lead)
        platform = platform_display(lead)
        date = date_display(lead)
        urgency = stars(lead.get("urgency_score", 0))
        confidence = confidence_pct(lead.get("confidence", 0))
        whatsapp = contact_display(lead, "possible_whatsapp")
        phone = contact_display(lead, "possible_phone")
        profile = lead.get("profile_link", "No disponible")
        post = lead.get("post_link", "No disponible")
        quote = quote_clean(lead)

        # Markdown version
        lines_md.append(f"### Lead #{i}")
        lines_md.append("")
        lines_md.append(f"**Problema:** {problem}  ")
        lines_md.append(f"**Persona:** {person}  ")
        lines_md.append(f"**Provincia:** {province} | **Ciudad:** {city}  ")
        lines_md.append(f"**Vehículo:** {vehicle} | **Plataforma:** {platform}  ")
        lines_md.append(f"**Fecha:** {date}  ")
        lines_md.append(f"**Urgencia:** {urgency}  ")
        lines_md.append(f"**Confianza:** {confidence}  ")
        lines_md.append(f"**WhatsApp:** {whatsapp}  ")
        lines_md.append(f"**Teléfono:** {phone}  ")
        lines_md.append(f"**Perfil:** {profile if profile else 'No disponible'}  ")
        lines_md.append(f"**Publicación:** {post}  ")
        lines_md.append("")
        lines_md.append(f"> {quote}")
        lines_md.append("")
        lines_md.append("---")
        lines_md.append("")

        # Texto plano
        lines_txt.append(f"  Lead #{i}")
        lines_txt.append(f"  Problema: {problem}")
        lines_txt.append(f"  Persona: {person}")
        lines_txt.append(f"  Provincia: {province} | Ciudad: {city}")
        lines_txt.append(f"  Vehiculo: {vehicle} | Plataforma: {platform}")
        lines_txt.append(f"  Fecha: {date}")
        lines_txt.append(f"  Urgencia: {urgency}")
        lines_txt.append(f"  Confianza: {confidence}")
        lines_txt.append(f"  WhatsApp: {whatsapp}")
        lines_txt.append(f"  Telefono: {phone}")
        lines_txt.append(f"  Perfil: {profile}")
        lines_txt.append(f"  Publicacion: {post}")
        lines_txt.append(f"  Comentario:")
        # Wrap quote en texto plano
        for line_wrap in [quote[i:i+68] for i in range(0, len(quote), 68)]:
            lines_txt.append(f"    {line_wrap}")
        lines_txt.append("")

    # ===== SECCIÓN 2: LEADS COMERCIALES =====
    lines_md.append("## 🟡 LEADS COMERCIALES")
    lines_md.append("")
    lines_md.append(f"_{len(commercial_signals)} señales preventivas: personas vendiendo o permutando vehículos (sin dolor explícito declarado, pero con posible necesidad futura de gestión)._")
    lines_md.append("")

    lines_txt.append("-" * 70)
    lines_txt.append("  LEADS COMERCIALES (preventivos)")
    lines_txt.append("-" * 70)
    lines_txt.append(f"  {len(commercial_signals)} senales preventivas.")
    lines_txt.append("")

    for i, lead in enumerate(commercial_signals, 1):
        problem = problem_short(lead)
        province = province_display(lead)
        vehicle = vehicle_display(lead)
        platform = platform_display(lead)
        whatsapp = contact_display(lead, "possible_whatsapp")
        phone = contact_display(lead, "possible_phone")
        post = lead.get("post_link", "No disponible")
        quote = quote_clean(lead, max_len=120)

        # Versión compacta (los comerciales van en una línea cada uno)
        contact_info = []
        if lead.get("possible_whatsapp"):
            contact_info.append(f"WA: {lead['possible_whatsapp']}")
        if lead.get("possible_phone"):
            contact_info.append(f"Tel: {lead['possible_phone']}")
        contact_str = " | ".join(contact_info) if contact_info else "Sin contacto público"

        lines_md.append(f"**Lead #{i}** — {problem}  ")
        lines_md.append(f"📍 {province} | 🚗 {vehicle} | 📱 {platform} | {contact_str}  ")
        lines_md.append(f"📝 _{quote}_  ")
        lines_md.append(f"🔗 {post}")
        lines_md.append("")

        lines_txt.append(f"  Lead #{i}: {problem}")
        lines_txt.append(f"    Provincia: {province} | Vehiculo: {vehicle} | Plataforma: {platform}")
        lines_txt.append(f"    Contacto: {contact_str}")
        lines_txt.append(f"    Publicacion: {post}")
        lines_txt.append("")

    # ===== SECCIÓN 3: CONTACTOS PÚBLICOS =====
    contacts = []
    for lead in real_leads + commercial_signals:
        wa = lead.get("possible_whatsapp", "")
        ph = lead.get("possible_phone", "")
        if wa or ph:
            contacts.append({
                "persona": person_display(lead),
                "whatsapp": wa or "—",
                "telefono": ph or "—",
                "perfil": lead.get("profile_link", "—"),
                "plataforma": platform_display(lead),
            })

    lines_md.append("## 📞 CONTACTOS PÚBLICOS ENCONTRADOS")
    lines_md.append("")
    lines_md.append(f"_{len(contacts)} personas con contacto publicado (solo si fue publicado por la propia persona en su post público)._")
    lines_md.append("")
    if contacts:
        lines_md.append("| Persona | WhatsApp | Teléfono | Plataforma | Perfil |")
        lines_md.append("|---------|----------|----------|------------|--------|")
        for c in contacts:
            perfil_short = c["perfil"][:40] + "…" if len(c["perfil"]) > 40 else c["perfil"]
            lines_md.append(f"| {c['persona']} | {c['whatsapp']} | {c['telefono']} | {c['plataforma']} | {perfil_short} |")
    else:
        lines_md.append("_No se encontraron contactos públicos en este lote._")
    lines_md.append("")

    lines_txt.append("-" * 70)
    lines_txt.append("  CONTACTOS PUBLICOS ENCONTRADOS")
    lines_txt.append("-" * 70)
    lines_txt.append(f"  {len(contacts)} personas con contacto publicado.")
    lines_txt.append("")
    if contacts:
        lines_txt.append(f"  {'Persona':<25} {'WhatsApp':<18} {'Teléfono':<18} {'Plataforma':<12}")
        lines_txt.append(f"  {'-'*25} {'-'*18} {'-'*18} {'-'*12}")
        for c in contacts:
            lines_txt.append(f"  {c['persona'][:25]:<25} {c['whatsapp'][:18]:<18} {c['telefono'][:18]:<18} {c['plataforma'][:12]:<12}")
    else:
        lines_txt.append("  No se encontraron contactos publicos.")
    lines_txt.append("")

    # ===== SECCIÓN 4: RESUMEN =====
    platform_counts = {}
    for lead in real_leads + commercial_signals:
        p = platform_display(lead)
        platform_counts[p] = platform_counts.get(p, 0) + 1

    reason_counts = {}
    for lead in real_leads:
        r = lead.get("lead_reason", "")
        reason_counts[r] = reason_counts.get(r, 0) + 1

    lines_md.append("## 📊 RESUMEN")
    lines_md.append("")
    lines_md.append(f"- **Leads calientes (dolor explícito):** {len(real_leads)}")
    lines_md.append(f"- **Leads comerciales (preventivos):** {len(commercial_signals)}")
    lines_md.append(f"- **Contactos públicos encontrados:** {len(contacts)}")
    lines_md.append("")
    lines_md.append("**Por plataforma:**")
    for p, n in sorted(platform_counts.items(), key=lambda x: -x[1]):
        lines_md.append(f"- {p}: {n}")
    lines_md.append("")
    lines_md.append("**Tipos de dolor (leads calientes):**")
    reason_labels = {
        "declara_multas": "Declaró multas/fotomultas",
        "declara_problema_transferencia": "Problema con transferencia",
        "declara_problema_libre_deuda": "Necesita libre deuda",
        "consulta_documentacion": "Consulta documentación",
    }
    for r, n in sorted(reason_counts.items(), key=lambda x: -x[1]):
        label = reason_labels.get(r, r)
        lines_md.append(f"- {label}: {n}")
    lines_md.append("")
    lines_md.append("---")
    lines_md.append("")
    lines_md.append("_Este reporte fue generado automáticamente por el Radar de Oportunidades v4.1._")
    lines_md.append("_Todas las publicaciones son de fuentes públicas. No se accedió a contenido privado._")
    lines_md.append("_La revisión humana es obligatoria antes de cualquier contacto._")

    lines_txt.append("=" * 70)
    lines_txt.append("  RESUMEN")
    lines_txt.append("=" * 70)
    lines_txt.append(f"  Leads calientes (dolor explicito): {len(real_leads)}")
    lines_txt.append(f"  Leads comerciales (preventivos):  {len(commercial_signals)}")
    lines_txt.append(f"  Contactos publicos:               {len(contacts)}")
    lines_txt.append("")
    lines_txt.append("  Por plataforma:")
    for p, n in sorted(platform_counts.items(), key=lambda x: -x[1]):
        lines_txt.append(f"    {p}: {n}")
    lines_txt.append("")
    lines_txt.append("  Tipos de dolor (leads calientes):")
    for r, n in sorted(reason_counts.items(), key=lambda x: -x[1]):
        label = reason_labels.get(r, r)
        lines_txt.append(f"    {label}: {n}")
    lines_txt.append("")
    lines_txt.append("=" * 70)
    lines_txt.append("  Este reporte fue generado automaticamente por el Radar de Oportunidades v4.1")
    lines_txt.append("  Todas las publicaciones son de fuentes publicas.")
    lines_txt.append("  La revision humana es obligatoria antes de cualquier contacto.")
    lines_txt.append("=" * 70)

    # Guardar archivos
    md_content = "\n".join(lines_md)
    txt_content = "\n".join(lines_txt)

    OUTPUT_PATH.write_text(md_content, encoding="utf-8")
    OUTPUT_TXT_PATH.write_text(txt_content, encoding="utf-8")

    print(f"✓ Reporte Markdown: {OUTPUT_PATH}", file=sys.stderr)
    print(f"✓ Reporte texto plano: {OUTPUT_TXT_PATH}", file=sys.stderr)
    print(f"✓ Leads calientes: {len(real_leads)}", file=sys.stderr)
    print(f"✓ Leads comerciales: {len(commercial_signals)}", file=sys.stderr)
    print(f"✓ Contactos públicos: {len(contacts)}", file=sys.stderr)

    # También imprimir el contenido a stdout para que el usuario lo vea
    print(md_content)


if __name__ == "__main__":
    generate_report()
