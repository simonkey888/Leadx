FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    LEADX_REPO_ROOT=/app \
    LEADX_STATE_DIR=/state \
    LEADX_INTERVAL_MINUTES=180 \
    LEADX_TIMEOUT_SECONDS=260 \
    LEADX_MAX_HEALTH_AGE_MINUTES=240

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 leadx \
    && useradd --system --uid 10001 --gid leadx --home-dir /nonexistent --shell /usr/sbin/nologin leadx \
    && mkdir -p /app /state \
    && chown -R leadx:leadx /app /state

WORKDIR /app

COPY --chown=leadx:leadx generate_payload.py /app/generate_payload.py
COPY --chown=leadx:leadx labs /app/labs

RUN chmod 0555 /app/labs/fotomultas_discovery/container/entrypoint.sh \
    && find /app -type d -exec chmod 0555 {} + \
    && find /app -type f ! -path '*/entrypoint.sh' -exec chmod 0444 {} +

USER 10001:10001
VOLUME ["/state"]

HEALTHCHECK --interval=5m --timeout=15s --start-period=7m --retries=2 \
  CMD python -m labs.fotomultas_discovery.healthcheck \
      --candidates /state/candidates-latest.json \
      --decisions /state/fotomultas-decisions.json \
      --max-age-minutes "$LEADX_MAX_HEALTH_AGE_MINUTES" || exit 1

ENTRYPOINT ["/app/labs/fotomultas_discovery/container/entrypoint.sh"]
