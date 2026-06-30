"""
mock_sources.py — Generador de señales sintéticas + stubs documentados para Fase 2/3.

Filosofía:
- Fase 1 (este archivo): genera señales mock realistas en español AR para validar
  extracción, scoring, dedup, review queue y audit trail SIN tocar plataformas reales.
- Fases 2/3: los conectores reales (Facebook, X, marketplace, foros, news) se documentan
  como stubs con la firma exacta que deberían tener, pero no se ejecutan. Ver
  `RealSourceStub` al final del archivo.

Compliance: todas las señales mock usan datos sintéticos. Ningún dato real de personas
reales es recolectado o generado.
"""
from __future__ import annotations
import hashlib
import json
import random
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional, Callable
from dataclasses import asdict

from models import Signal, now_iso, AR_TZ
import config

random.seed(42)  # reproducibilidad para Fase 1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(days_ago: int, hour: int = 10) -> str:
    dt = datetime.now(AR_TZ) - timedelta(days=days_ago)
    dt = dt.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59), microsecond=0)
    return dt.isoformat()


def _url(source_id: str, slug: str) -> str:
    h = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:10]
    return f"https://{source_id.replace('_', '.')}/post/{h}"


# ---------------------------------------------------------------------------
# Plantillas de señales mock realistas (español AR)
# ---------------------------------------------------------------------------
# Cada plantilla produce 1-N señales. Las señales se mezclan y se randomizan.
# Las patentes usan formato AR. Las jurisdicciones son las del spec.

TEMPLATES: List[Dict[str, Any]] = [
    # --- Facebook public groups -------------------------------------------------
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Mariela G.",
        "profile_url_tpl": "https://facebook.com/profile.php?id=1000{rand}",
        "text": "Hola gente, tengo una fotomulta de CABA del mes pasado, no sé cómo hacer el reclamo. Me llegó a mi domicilio de Caballito. Alguien sabe si conviene ir a defenderme o pagar? Son $18.500.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Caballito",
        "problem_hint": "fotomulta",
        "amount_hint": 18500,
        "days_ago": 2,
    },
    {
        "source_id": "facebook_public_groups",
        "author_alias": "El Tano Automotores",
        "profile_url_tpl": "https://facebook.com/eltanoautomotores",
        "text": "Vendo Ford Fiesta Kinetic 2015, tengo el libre deuda al día, listo para transferir. Patente ABC 123. Estoy en Lanús. Mandar MP.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "Lanús",
        "problem_hint": "transferencia",
        "amount_hint": None,
        "days_ago": 1,
    },
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Caro",
        "profile_url_tpl": "https://facebook.com/profile.php?id=2000{rand}",
        "text": "Consulto por una multa de ruta en la 2, me dicen que son de APSV pero nunca me llegó la notificación. Vivo en Rosario. Alguien pasó lo mismo?",
        "jurisdiction_hint": "SANTA_FE",
        "locality_hint": "Rosario",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 4,
    },
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Jorge M.",
        "profile_url_tpl": "https://facebook.com/profile.php?id=3000{rand}",
        "text": "Gente, no puedo renovar el registro porque tengo 3 multas impagas de Córdoba capital. Alguien sabe si hay plan de pago? Son como $45.000 en total.",
        "jurisdiction_hint": "CORDOBA",
        "locality_hint": "Córdoba",
        "problem_hint": "regularizacion",
        "amount_hint": 45000,
        "days_ago": 3,
    },
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Anónimo (no comparte perfil)",
        "profile_url_tpl": "",
        "text": "Multas de fotomulta en PBA, me llegaron 5 de una sola vez, todas de la misma cámara en Panamericana. Alguien sabe si se puede reclamar? Vivo en San Martín.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "San Martín",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 5,
    },

    # --- Marketplace -----------------------------------------------------------
    {
        "source_id": "marketplace_public_posts",
        "author_alias": "Lucía Ventas",
        "profile_url_tpl": "https://marketplace.com/user/lucia_ventas",
        "text": "Vendo auto Peugeot 208 2019. Libre deuda y 08 firmado, listo para transferir. Sin deudas. $4.500.000. Zona Villa Crespo.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Villa Crespo",
        "problem_hint": "transferencia",
        "amount_hint": 4500000,
        "days_ago": 1,
    },
    {
        "source_id": "marketplace_public_posts",
        "author_alias": "Diego A.",
        "profile_url_tpl": "https://marketplace.com/user/diego_a",
        "text": "Vendo moto Honda CG 150 titán 2018. Patente AB 456 CD. Le debo 2 cuotas de patente de PBA, lo regularizo antes de transferir. Avisanos.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "",
        "problem_hint": "patente",
        "amount_hint": None,
        "days_ago": 2,
    },
    {
        "source_id": "marketplace_public_posts",
        "author_alias": "VendoYa Autoplanes",
        "profile_url_tpl": "https://marketplace.com/user/vendoya",
        "text": "Toyota Corolla 2020, transferir con libre deuda al día. Cliente necesita urgente, se muda al sur. Precio conversable.",
        "jurisdiction_hint": "",
        "locality_hint": "",
        "problem_hint": "transferencia",
        "amount_hint": None,
        "days_ago": 1,
    },

    # --- X / Twitter -----------------------------------------------------------
    {
        "source_id": "x_search",
        "author_alias": "@usuario_cabildo",
        "profile_url_tpl": "https://x.com/usuario_cabildo",
        "text": "Otra fotomulta en Cabildo y Juramento. Tercera en 2 meses. @GCBAComunas cómo hago el reclamo?? #fotomultas #CABA",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Belgrano",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 1,
    },
    {
        "source_id": "x_search",
        "author_alias": "@radares_arg",
        "profile_url_tpl": "https://x.com/radares_arg",
        "text": "Listado de radares nuevos en Panamericana. Cuidado con las multas gente, ya caen varias. #APSV #multas",
        "jurisdiction_hint": "PBA",
        "locality_hint": "",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 6,
    },
    {
        "source_id": "x_search",
        "author_alias": "@martinros",
        "profile_url_tpl": "https://x.com/martinros",
        "text": "Me llegó una multa de la ciudad de Rosario pero yo nunca estuve ahí. Alguien sabe cómo defenderse? #santafe",
        "jurisdiction_hint": "SANTA_FE",
        "locality_hint": "Rosario",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 3,
    },

    # --- Public forums --------------------------------------------------------
    {
        "source_id": "public_forums",
        "author_alias": "foro_user_8821",
        "profile_url_tpl": "https://foro-auto.com.ar/user/foro_user_8821",
        "text": "No puedo renovar el registro porque tengo 2 multas de Córdoba que no me llegaron nunca. Fui a hacer el trámite y me aparecen. Cómo las regularizo? Son del 2023.",
        "jurisdiction_hint": "CORDOBA",
        "locality_hint": "Córdoba",
        "problem_hint": "regularizacion",
        "amount_hint": None,
        "days_ago": 7,
    },
    {
        "source_id": "public_forums",
        "author_alias": "comunidad_motorista",
        "profile_url_tpl": "https://foro-motos.com/user/comunidad_motorista",
        "text": "Consulto por multa de ruta en RN8, la cámara me tomó a 110 km/h donde era 100. Vale la pena defenderla? Patente AB 789 EF. Vivo en Pilar.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "Pilar",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 4,
    },
    {
        "source_id": "public_forums",
        "author_alias": "transferencias_dudas",
        "profile_url_tpl": "https://foro-auto.com.ar/user/transferencias_dudas",
        "text": "Para transferir un auto necesito libre deuda, pero el dueño anterior dejó multas impagas. Quién las paga? Es en CABA.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "",
        "problem_hint": "transferencia",
        "amount_hint": None,
        "days_ago": 2,
    },
    {
        "source_id": "public_forums",
        "author_alias": "anon_foro",
        "profile_url_tpl": "",
        "text": "Alguien sabe el costo del libre deuda en Mendoza? Tengo que transferir una camioneta y no sé los aranceles.",
        "jurisdiction_hint": "MENDOZA",
        "locality_hint": "Mendoza",
        "problem_hint": "libre_deuda",
        "amount_hint": None,
        "days_ago": 8,
    },

    # --- News + comments -----------------------------------------------------
    {
        "source_id": "news_and_comments",
        "author_alias": "infobae_comment_8821",
        "profile_url_tpl": "",
        "text": "Comentario en nota sobre radares: 'A mí me clavaron 3 en el mismo lugar sin cartel de aviso. Denuncia presentada en defensoría'.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 5,
    },
    {
        "source_id": "news_and_comments",
        "author_alias": "lanacion_comment_4455",
        "profile_url_tpl": "",
        "text": "Reclamo colectivo por fotomultas en Acceso Oeste. Vecinos de Moreno y Ituzaingó se organizan para presentación judicial.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "Moreno",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 9,
    },
    {
        "source_id": "news_and_comments",
        "author_alias": "cronista_comment_1199",
        "profile_url_tpl": "",
        "text": "Denuncia en defensoría del pueblo de CABA por cobro de multas sin notificación previa. Suma 12 reclamos.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "CABA",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 12,
    },

    # --- Duplicados intencionales (para probar dedup) -------------------------
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Mariela G.",
        "profile_url_tpl": "https://facebook.com/profile.php?id=1000{rand}",
        "text": "Hola gente, tengo una fotomulta de CABA del mes pasado, no sé cómo hacer el reclamo. Me llegó a mi domicilio de Caballito. Alguien sabe si conviene ir a defenderme o pagar? Son $18.500.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Caballito",
        "problem_hint": "fotomulta",
        "amount_hint": 18500,
        "days_ago": 0,  # mismo día: simulamos repost
        "_duplicate_of_text": True,
    },
    {
        "source_id": "x_search",
        "author_alias": "@usuario_cabildo",
        "profile_url_tpl": "https://x.com/usuario_cabildo",
        "text": "Otra fotomulta en Cabildo y Juramento. Tercera en 2 meses. @GCBAComunas cómo hago el reclamo?? #fotomultas #CABA",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Belgrano",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 0,
        "_duplicate_of_text": True,
    },

    # --- Caso crítico comercial (score esperado >=80) -------------------------
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Vendedor Rafaela",
        "profile_url_tpl": "https://facebook.com/profile.php?id=5000{rand}",
        "text": "URGENTE: vendo auto por traslado al exterior. Tengo libre deuda pendiente en Santa Fe, necesito regularizar y transferir antes del 15 del mes que viene. Auto en Rafaela, patente ABC 999. Escucho ofertas.",
        "jurisdiction_hint": "SANTA_FE",
        "locality_hint": "Rafaela",
        "problem_hint": "transferencia",
        "amount_hint": None,
        "days_ago": 0,
    },
    {
        "source_id": "marketplace_public_posts",
        "author_alias": "Familia Pérez",
        "profile_url_tpl": "https://marketplace.com/user/familia_perez",
        "text": "VENDO URGENTE Ford EcoSport 2018. Libre deuda vencido, hay 2 multas en CABA que necesito regularizar antes de transferir. Zona Flores. Atiendo consultas hoy.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Flores",
        "problem_hint": "regularizacion",
        "amount_hint": None,
        "days_ago": 0,
    },

    # --- Señales que deben ser RECHAZADAS por privacy filter ------------------
    {
        "source_id": "facebook_public_groups",
        "author_alias": "usuario_test_pii",
        "profile_url_tpl": "",
        "text": "Hola, mi DNI es 30.123.456 y me llegó una multa. Pasen datos por privado por favor. Tel: +54 11 5555-1234.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 1,
        "_should_be_rejected": True,
    },
    {
        "source_id": "x_search",
        "author_alias": "@anon_pii",
        "profile_url_tpl": "",
        "text": "Contacto: juan.perez@example.com para asesoramiento sobre multas. CUIT 20-12345678-5.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 2,
        "_should_be_rejected": True,
    },
]


# ---------------------------------------------------------------------------
# Generador
# ---------------------------------------------------------------------------
def generate_mock_signals() -> List[Signal]:
    """Genera la lista de señales mock para Fase 1."""
    signals: List[Signal] = []
    for i, t in enumerate(TEMPLATES):
        rand_suffix = f"{random.randint(10000, 99999)}"
        profile_url = t["profile_url_tpl"].replace("{rand}", rand_suffix) if t["profile_url_tpl"] else ""
        text = t["text"]
        slug = f"{t['source_id']}|{text[:60]}|{i}"
        sig = Signal(
            source_id=t["source_id"],
            source_url=_url(t["source_id"], slug),
            raw_text=text,
            author_alias=t["author_alias"],
            profile_url=profile_url,
            detected_at=now_iso(),
            signal_keywords=[k for k in config.SOURCES if k["id"] == t["source_id"]][0]["signals"],
            raw_metadata={
                "published_at": _ts(t["days_ago"]),
                "jurisdiction_hint": t["jurisdiction_hint"],
                "locality_hint": t["locality_hint"],
                "problem_hint": t["problem_hint"],
                "amount_hint": t["amount_hint"],
                "_duplicate_of_text": t.get("_duplicate_of_text", False),
            },
        )
        signals.append(sig)
    random.shuffle(signals)
    return signals


# ---------------------------------------------------------------------------
# Stubs para conectores reales (Fases 2/3)
# ---------------------------------------------------------------------------
class RealSourceStub:
    """
    Stubs documentados de conectores reales para Fases 2 y 3.

    Cada método tiene la firma y comportamiento esperados, pero NO se ejecuta.
    El equipo de operación debe implementar la lógica real respetando:
    - Solo contenido público o accesible con consentimiento legítimo
    - Sin scraping de perfiles privados
    - Respeto a los Términos de Servicio de cada plataforma
    - Rate limiting y backoff exponencial
    - Logging completo al audit trail

    Para activar un conector en Fase 2/3:
    1. Implementar el método `_fetch_*` con la API oficial del plataforma
    2. Reemplazar la firma del método público (sin _ inicial)
    3. Agregar credenciales a config.py
    4. Documentar el alcance legal en el README
    """

    @staticmethod
    def fetch_facebook_public_groups(group_ids: List[str], since_hours: int = 24) -> List[Signal]:
        """
        Fase 2/3 — Conector real para Facebook Public Groups.

        ⚠️ No implementado en Fase 1. Consideraciones:
        - Facebook Graph API no expone búsqueda pública de grupos sin app review
        - Alternativa viable: usar CrowdTangle (descontinuado) o Meta Content Library
          (solo para investigadores acreditados)
        - Alternativa práctica Fase 2: miembro humano del equipo con acceso legítimo
          al grupo pega las señales relevantes en la Google Sheet
        - Alternativa Fase 3: integración con Meta Content Library API si se obtiene
          acceso investigador

        Args:
            group_ids: IDs de grupos públicos donde el negocio tiene acceso legítimo
            since_hours: ventana de tiempo hacia atrás

        Returns:
            Lista de Signal crudas, con source_id="facebook_public_groups"
        """
        raise NotImplementedError(
            "Conector Facebook real requiere acceso investigador a Meta Content Library "
            "o ingreso manual por miembro del equipo con acceso legítimo al grupo."
        )

    @staticmethod
    def fetch_x_search(query: str, since_hours: int = 24) -> List[Signal]:
        """
        Fase 2/3 — Conector real para X (Twitter) Search.

        Viable vía X API v2 (tier Basic $100/mes o Pro $5000/mes).
        Endpoint: GET /2/tweets/search/recent
        Requiere Bearer Token en env var X_BEARER_TOKEN.

        Args:
            query: query de búsqueda con operadores de X (lang:es -is:retweet, etc.)
            since_hours: ventana de tiempo hacia atrás (máx 7 días en tier Basic)

        Returns:
            Lista de Signal con source_id="x_search"
        """
        raise NotImplementedError(
            "Conector X real requiere X_API_BEARER_TOKEN. "
            "Ver https://developer.x.com/en/docs/x-api"
        )

    @staticmethod
    def fetch_marketplace_public_posts(keywords: List[str], since_hours: int = 24) -> List[Signal]:
        """
        Fase 2/3 — Conector real para Marketplace.

        ⚠️ Facebook Marketplace no expone API pública de búsqueda.
        Alternativas viables:
        - Scraping con Playwright + sesión autenticada (violaría ToS de Meta)
        - Ingreso manual por operador del equipo
        - Monitoreo de grupos de Marketplace vía API de grupos (ver fetch_facebook_public_groups)

        Returns:
            Lista de Signal con source_id="marketplace_public_posts"
        """
        raise NotImplementedError(
            "Marketplace no tiene API pública. Usar ingreso manual en Fase 2."
        )

    @staticmethod
    def fetch_public_forums(forum_rss_urls: List[str], since_hours: int = 24) -> List[Signal]:
        """
        Fase 2/3 — Conector real para foros públicos vía RSS/Atom.

        ✓ Viable y recomendado. La mayoría de foros (phpBB, Discourse, etc.) exponen RSS.
        Implementar con feedparser + filtros por keywords.

        Args:
            forum_rss_urls: lista de URLs RSS de foros públicos
            since_hours: ventana de tiempo hacia atrás

        Returns:
            Lista de Signal con source_id="public_forums"
        """
        raise NotImplementedError(
            "Implementar con feedparser. RSS URLs a configurar en config.py FORUM_RSS_URLS."
        )

    @staticmethod
    def fetch_news_and_comments(news_rss_urls: List[str], since_hours: int = 24) -> List[Signal]:
        """
        Fase 2/3 — Conector real para noticias y comentarios vía RSS.

        ✓ Viable. Fuentes sugeridas:
        - Infobae, La Nación, Clarín: secciones policía/tránsito
        - Defensoría del Pueblo de CABA y PBA: RSS de comunicados
        - Agencias provinciales de seguridad vial

        Returns:
            Lista de Signal con source_id="news_and_comments"
        """
        raise NotImplementedError(
            "Implementar con feedparser + parser de comentarios si disponible."
        )


# ---------------------------------------------------------------------------
# Selector de fuente (mock en Fase 1, real en Fase 2/3)
# ---------------------------------------------------------------------------
def collect_signals(use_real: bool = False, **kwargs) -> List[Signal]:
    """
    Punto de entrada del collector.

    Fase 1 (use_real=False): devuelve señales mock.
    Fase 2/3 (use_real=True): intenta usar conectores reales (requiere credenciales).
    """
    if not use_real:
        return generate_mock_signals()

    # Fase 2/3 — llamada a conectores reales
    signals: List[Signal] = []
    stub = RealSourceStub()
    try:
        signals.extend(stub.fetch_x_search(query="fotomulta OR libre deuda OR transferencia", **kwargs))
    except NotImplementedError as e:
        print(f"  [warn] X no disponible: {e}")
    try:
        signals.extend(stub.fetch_public_forums(forum_rss_urls=[], **kwargs))
    except NotImplementedError as e:
        print(f"  [warn] Foros no disponible: {e}")
    try:
        signals.extend(stub.fetch_news_and_comments(news_rss_urls=[], **kwargs))
    except NotImplementedError as e:
        print(f"  [warn] News no disponible: {e}")
    return signals


if __name__ == "__main__":
    # Smoke test
    sigs = generate_mock_signals()
    print(f"Generadas {len(sigs)} señales mock")
    for s in sigs[:3]:
        print(f"  - {s.signal_id} [{s.source_id}] {s.raw_text[:80]}...")
