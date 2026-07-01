# QuestSync — Radicale + the Habitica-backed storage/auth plugins.
#
# Multi-stage: the default target (`prod`) has NO demo gate, so QUESTSYNC_DEMO=1
# does nothing there. The `dev` target bakes a marker file that enables demo
# mode for local use — so the accept-any-auth bypass can never be turned on in a
# production image by a single env var. CI builds the default (prod) target.
FROM python:3.12-slim AS base
RUN pip install --no-cache-dir "radicale<4" "python-dateutil>=2.8"
COPY src/ /app/
COPY radicale/config /etc/radicale/config
ENV PYTHONPATH=/app
EXPOSE 5232
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:5232/.web/', timeout=4).status==200 else 1)"
CMD ["radicale", "--config", "/etc/radicale/config"]

# Local-dev image: enables the build-gated demo mode (accept-any-auth + fixtures).
# Marker lives outside /app so the compose src bind-mount can't shadow it.
FROM base AS dev
RUN install -d /etc/questsync && touch /etc/questsync/demo-allowed

# Production image (default build target): demo mode is impossible here.
FROM base AS prod
