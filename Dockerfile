FROM python:3.11-slim-bookworm AS build
WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ephemerides.sha256 ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt
RUN mkdir ephe \
    && for asset in sepl_18.se1 semo_18.se1; do \
         curl --fail --silent --show-error --location --retry 3 --max-time 30 \
           "https://raw.githubusercontent.com/aloistr/swisseph/6c9897279736b76e81f0b0039d05283a9ba59dc5/ephe/$asset" \
           --output "ephe/$asset" || exit 1; \
       done \
    && sha256sum --check ephemerides.sha256

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data EPHE_DIR=/app/ephe
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 astro \
    && useradd --uid 10001 --gid 10001 --no-create-home astro \
    && install -d -o astro -g astro /data
COPY requirements.txt .
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt
COPY --from=build /build/ephe ./ephe
COPY app.py astronomy.py photos.py publish.py upstream.py index.html LICENSE ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=3).close()"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "app:app"]
