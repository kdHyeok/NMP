#!/usr/bin/env bash
set -euo pipefail
root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
mode="${1:-local}"
case "$mode" in local|tunnel|server) ;; *) echo 'Usage: bash scripts/install.sh [local|tunnel|server]' >&2; exit 2 ;; esac
if ! command -v uv >/dev/null 2>&1; then
    echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2
    exit 1
fi
if [ "$mode" = server ]; then
    if [ "$(uname -s)" != Linux ]; then echo 'Server mode requires Linux.' >&2; exit 1; fi
    docker info >/dev/null
    docker compose version >/dev/null
fi
uv sync --frozen
uv run --frozen python -B -m naver_mail_mcp.cli setup --mode "$mode"
uv run --frozen python -B -m naver_mail_mcp.cli doctor
if [ "$mode" = server ]; then
    docker compose --env-file .nmp/compose.env up -d --build
    docker compose --env-file .nmp/compose.env ps
elif [ "$mode" = tunnel ]; then
    echo 'Run: uv run --frozen nmp tunnel'
else
    echo 'Import .nmp/mcp.json into your local MCP client.'
fi