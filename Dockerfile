FROM python:3.12-slim

WORKDIR /app

ARG SESSION_BROWSER_VERSION=0.0.0-dev

LABEL org.opencontainers.image.title="session-browser"
LABEL org.opencontainers.image.description="Local Claude/Codex/Qoder session browser"
LABEL org.opencontainers.image.source="https://github.com/iampkuhz/feipi-session-browser"

# Runtime dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY VERSION ./
COPY src/ src/
COPY scripts/ scripts/

# Make scripts executable
RUN chmod +x scripts/session-browser.sh

# Runtime config
ENV SERVER_HOST=0.0.0.0
ENV SERVER_PORT=8899
ENV SESSION_BROWSER_VERSION=${SESSION_BROWSER_VERSION}
ENV SESSION_BROWSER_LOG_LEVEL=INFO
ENV SESSION_BROWSER_RUN_MODE=podman

# Data directories will be mounted at runtime
ENV CLAUDE_DATA_DIR=/data/claude
ENV CODEX_DATA_DIR=/data/codex
ENV QODER_DATA_DIR=/data/qoder
ENV INDEX_DIR=/data/index

EXPOSE 8899

# Default: start web server with a startup scan (requires data volumes mounted)
CMD ["./scripts/session-browser.sh", "serve", "--allow-empty", "--startup-scan"]
