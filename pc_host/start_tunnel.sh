#!/usr/bin/env bash
set -euo pipefail

HTTP_PORT="${1:-8000}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is not installed. Install it with: brew install cloudflared" >&2
  exit 1
fi

echo "Starting Cloudflare Quick Tunnel to http://localhost:${HTTP_PORT} ..."
echo "Copy the https://*.trycloudflare.com URL below and paste it into your dashboard."
exec cloudflared tunnel --url "http://localhost:${HTTP_PORT}"
