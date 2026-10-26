# syntax=docker/dockerfile:1
FROM python:3.12.15-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable --no-cache

ARG TARGETARCH
ARG TUNNEL_CLIENT_VERSION=0.0.17
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    case "$TARGETARCH" in amd64|arm64) ;; *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; esac; \
    archive="tunnel-client-v${TUNNEL_CLIENT_VERSION}-linux-${TARGETARCH}.zip"; \
    release="https://github.com/openai/tunnel-client/releases/download/v${TUNNEL_CLIENT_VERSION}"; \
    cd /tmp; \
    curl --fail --location --retry 3 "$release/$archive" -o "$archive"; \
    curl --fail --location --retry 3 "$release/SHA256SUMS.txt" -o SHA256SUMS.txt; \
    grep " $archive\$" SHA256SUMS.txt | sha256sum --check --strict -; \
    mkdir /opt/tunnel-client; \
    unzip -q "$archive" -d /opt/tunnel-client; \
    chmod 0555 /opt/tunnel-client/tunnel-client /opt/tunnel-client/cloudflared

FROM build AS test
COPY tests ./tests
COPY scripts ./scripts
CMD ["/app/.venv/bin/python", "-B", "-m", "unittest", "tests.test_unit", "tests.test_setup", "-v"]

FROM python:3.12.15-slim-bookworm AS runtime
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin nmp \
    && mkdir /run/nmp && chown 10001:10001 /run/nmp && chmod 0700 /run/nmp
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/LICENSE /app/LICENSE
COPY --from=build /opt/tunnel-client /opt/tunnel-client
ENV PATH="/app/.venv/bin:/opt/tunnel-client:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NMP_CONFIG_DIR=/run/nmp \
    HOME=/tmp
USER 10001:10001
CMD ["python", "-B", "-m", "naver_mail_mcp.cli", "tunnel"]
