# QuestSync — Radicale + the Habitica-backed storage plugin, self-contained.
# docker-compose bind-mounts src/ and the config over these for dev iteration;
# the baked copies make the image deployable to Kubernetes as-is.
FROM python:3.12-slim

# Pin the Radicale line we built the storage plugin against (see docs/design.md).
RUN pip install --no-cache-dir "radicale<4" "python-dateutil>=2.8"

COPY src/ /app/
COPY radicale/config /etc/radicale/config
ENV PYTHONPATH=/app

EXPOSE 5232

# No curl in slim; use python for the health probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:5232/.web/', timeout=4).status==200 else 1)"

CMD ["radicale", "--config", "/etc/radicale/config"]
