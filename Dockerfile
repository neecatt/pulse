# syntax=docker/dockerfile:1
# Pulse: one image serving the API and the web app. Configure with PULSE_*
# environment variables (see .env.example); keep state in the /data volume.

# 1. Build the web app. Bun installs dependencies; Node runs the build tools
#    (Vite needs Node APIs that this Bun version lacks), as in local development.
FROM node:26-slim AS web
COPY --from=oven/bun:1.1.6 /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /web
COPY frontend/package.json frontend/bun.lockb frontend/bunfig.toml ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

# 2. Runtime
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY backend/pyproject.toml backend/README.md ./backend/
COPY backend/src ./backend/src
RUN pip install ./backend && rm -rf ./backend
COPY --from=web /web/dist ./web

# Defaults for running in a container; every one can be overridden.
ENV PULSE_HOST=0.0.0.0 \
    PULSE_PORT=8000 \
    PULSE_DATA_DIR=/data \
    PULSE_DATABASE_URL=sqlite+aiosqlite:////data/pulse.db \
    PULSE_STATIC_DIR=/app/web \
    PULSE_SLURM_BACKEND=ssh

RUN useradd --create-home --uid 1000 pulse && mkdir /data && chown pulse:pulse /data
USER pulse
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["pulse", "serve"]
