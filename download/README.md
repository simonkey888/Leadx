# Radar de Oportunidades — Prototipo Fase 1

Prototipo operativo en Python que valida extracción, scoring, deduplicación y
cola de revisión con foco en fuentes públicas y trazabilidad.

## Contenido de este directorio

- `radar_prototipo_fase1/` — código del prototipo (12 archivos .py + 3 .md)
- `sample_data/` — outputs de ejemplo generados al ejecutar el pipeline

## Cómo empezar

```bash
cd radar_prototipo_fase1
python main.py                  # pipeline end-to-end
python main.py --review --demo  # demo de revisión humana (no interactivo)
python main.py --review         # CLI de revisión interactivo
```

Ver `radar_prototipo_fase1/README.md` para detalles completos.
