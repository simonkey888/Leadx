# Modelo de Scoring — Radar de Oportunidades

Implementa el scoring 0-100 definido en el spec, con 7 dimensiones ponderadas.

---

## Pesos (del spec)

| Dimensión              | Peso | Implementación en `scorer.py`                |
| ---------------------- | ---- | --------------------------------------------- |
| `explicit_intent`      | 30   | `score_explicit_intent()`                     |
| `urgency`              | 15   | `score_urgency()`                             |
| `jurisdiction_fit`     | 15   | `score_jurisdiction_fit()`                    |
| `evidence_quality`     | 10   | `score_evidence_quality()`                    |
| `commercial_potential` | 10   | `score_commercial_potential()`                |
| `channel_fit`          | 10   | `score_channel_fit()`                         |
| `signal_repetition`    | 10   | `score_signal_repetition()`                   |
| **Total**              | 100  |                                               |

Cada dimensión se puntúa **0..1** y se multiplica por su peso. La suma se
clampa a `[0, 100]`.

---

## Umbrales (del spec)

| Banda     | Score       | Acción sugerida                              |
| --------- | ----------- | --------------------------------------------- |
| critical  | ≥ 80        | Revisar en < 4h, contacto manual prioritario |
| high      | ≥ 60        | Revisar en < 24h, contacto manual            |
| medium    | ≥ 40        | Revisar en cola normal                        |
| low       | < 40        | Revisar批量 semanal, descartar si no aplica   |

---

## Lógica de cada dimensión

### `explicit_intent` (peso 30)

Detecta verbos/sustantivos de acción comercial en `evidence_text`:

**Keywords**:
- Venta/transferencia: `vendo`, `vender`, `venta`, `transferir`, `transferencia`, `traspaso`
- Regularización: `regularizar`, `regularización`, `regularizacion`, `necesito arreglar`
- Libre deuda: `libre deuda`, `necesito libre`, `sacar libre`
- Asesoramiento: `consulto`, `consulta`, `asesoramiento`, `necesito asesor`, `abogado`
- Defensa/reclamo: `defender`, `defensa`, `reclamar`, `reclamo`, `denuncia`, `apelar`

**Puntaje**:
- 0 matches → 0.0
- 1 match → 0.6 (60% del peso)
- 2+ matches → 1.0 (100% del peso)

### `urgency` (peso 15)

Detecta marcadores temporales de urgencia:

**Keywords**:
- Temporales: `urgente`, `hoy`, `mañana`, `ahora`, `ya`, `rápido`
- Plazos: `antes de`, `lo antes posible`, `vencimiento`, `vence`
- Contexto urgente: `mudanza`, `traslado`, `mudo`, `viaje`

**Puntaje**:
- 0 matches → 0.0
- 1 match → 0.5
- 2+ matches → 1.0

### `jurisdiction_fit` (peso 15)

Verifica si `case.jurisdiction` está en `TARGET_JURISDICTIONS`:

**Target jurisdictions** (config.py):
```python
TARGET_JURISDICTIONS = {"CABA", "PBA", "CORDOBA", "SANTA_FE"}
```

**Puntaje**:
- En target → 1.0
- Jurisdicción conocida pero no target → 0.2
- Sin jurisdicción → 0.0

### `evidence_quality` (peso 10)

Suma puntos por cada entidad presente en el caso:

| Entidad          | Puntos |
| ---------------- | ------ |
| `patent`         | 0.30   |
| `amount` (>0)    | 0.25   |
| `locality`       | 0.20   |
| `year`           | 0.15   |
| `vehicle_type`   | 0.10   |

Máximo: 1.0 (todas presentes).

### `commercial_potential` (peso 10)

Mapea `problem_type` a potencial comercial:

| Problem type                              | Puntaje base                |
| ----------------------------------------- | --------------------------- |
| `transferencia` / `regularizacion` / `libre_deuda` | 0.8 (alto valor)   |
| — con `amount` > 1.000.000                | 1.0 (monto alto, auto)      |
| `fotomulta` (sin repetición)              | 0.3 (bajo individual)       |
| `fotomulta` (con 2+ repeticiones)         | 0.7 (volumen = oportunidad) |
| Otro problema tipificado                  | 0.4                         |
| Sin problema tipificado                   | 0.0                         |

### `channel_fit` (peso 10)

Verifica si `source_id` es de alta prioridad:

**High priority sources** (spec):
- `facebook_public_groups`
- `marketplace_public_posts`
- `public_forums`

**Puntaje**:
- High priority → 1.0
- Medium priority (X, news) → 0.4

### `signal_repetition` (peso 10)

Recibe `repetition_count` (cantidad de señales previas del mismo perfil/source_url):

| Repetition count | Puntaje |
| ---------------- | ------- |
| 0                | 0.0     |
| 1                | 0.5     |
| 2                | 0.8     |
| 3+               | 1.0     |

> En Fase 1 este valor siempre es 0 (no hay historial). En Fase 2 se calcula
> con query a DB: `SELECT COUNT(*) FROM signals WHERE profile_url = ? AND
> detected_at < ?`.

---

## Ejemplo de scoring

### Caso crítico (score 84)

Texto: *"URGENTE: vendo auto por traslado al exterior. Tengo libre deuda
pendiente en Santa Fe, necesito regularizar y transferir antes del 15 del mes
que viene. Auto en Rafaela, patente ABC 999. Escucho ofertas."*

| Dimensión              | Raw  | Peso | Ponderado |
| ---------------------- | ---- | ---- | --------- |
| explicit_intent        | 1.0  | 30   | 30        |
| urgency                | 1.0  | 15   | 15        |
| jurisdiction_fit       | 1.0  | 15   | 15        |
| evidence_quality       | 0.60 | 10   | 6         |
| commercial_potential   | 0.80 | 10   | 8         |
| channel_fit            | 1.0  | 10   | 10        |
| signal_repetition      | 0.0  | 10   | 0         |
| **Total**              |      |      | **84**    |

**Banda**: critical (≥80)

### Caso medio (score 42)

Texto: *"Me llegó una multa de la ciudad de Rosario pero yo nunca estuve ahí.
Alguien sabe cómo defenderse? #santafe"*

| Dimensión              | Raw  | Peso | Ponderado |
| ---------------------- | ---- | ---- | --------- |
| explicit_intent        | 0.6  | 30   | 18        |
| urgency                | 0.0  | 15   | 0         |
| jurisdiction_fit       | 1.0  | 15   | 15        |
| evidence_quality       | 0.20 | 10   | 2         |
| commercial_potential   | 0.30 | 10   | 3         |
| channel_fit            | 0.4  | 10   | 4         |
| signal_repetition      | 0.0  | 10   | 0         |
| **Total**              |      |      | **42**    |

**Banda**: medium (≥40)

---

## Ajustes futuros

Los pesos actuales son los del spec original. En Fase 2 se recomienda:

1. **Calibración con datos reales**: después de 100 casos revisados manualmente,
   ajustar pesos con regresión logística sobre `approved/rejected`.
2. **Decaimiento temporal**: señales viejas (>30 días) deberían perder score
   por时效. Implementar con factor `exp(-days/30)` en `urgency`.
3. **Penalización por spam**: si un perfil emite >5 señales/día, sospechar
   spam y bajar `explicit_intent` a 0.5.
4. **Boost por monto**: montos >$5.000.000 (auto premium) deberían subir
   `commercial_potential` a 1.0 directamente.
