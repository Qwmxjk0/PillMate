#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE=${COMPOSE:-docker compose}
if [ -f .env ]; then set -a; . ./.env; set +a; fi

echo "⏬ Stopping & removing containers + named volumes…"
$COMPOSE down -v --remove-orphans || true

# ล้างโฟลเดอร์ bind‑mount
if [ -n "${BIND_DATA_DIRS:-}" ]; then
  IFS=',' read -ra DIRS <<< "$BIND_DATA_DIRS"
  for d in "${DIRS[@]}"; do
    d="$(echo "$d" | xargs)"
    [ -z "$d" ] && continue
    [[ "$d" = "/" || "$d" = "." ]] && { echo "❌ ปฏิเสธการล้าง '$d'"; exit 1; }
    if [ -d "$d" ]; then
      echo "🧹 Wiping $d"
      find "$d" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    fi
  done
fi

echo "✅ Stack is down and data wiped."
