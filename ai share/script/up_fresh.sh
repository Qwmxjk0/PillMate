#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE=${COMPOSE:-docker compose}   # ใช้ docker compose (v2). ถ้า v1 ให้ export COMPOSE=docker-compose

# โหลด .env ถ้ามี
if [ -f .env ]; then set -a; . ./.env; set +a; fi

ZIP_DEFAULT="./drugbank_data/drugbank_all_full_database.xml.zip"
ZIP_PATH="${ZIP_PATH:-$ZIP_DEFAULT}"

# เช็คของจำเป็น
: "${MARIADB_ROOT_PASSWORD:?MARIADB_ROOT_PASSWORD ไม่ได้ตั้งค่าใน .env}"
: "${DB_NAME:?DB_NAME ไม่ได้ตั้งค่าใน .env}"
[ -f "$ZIP_PATH" ] || { echo "❌ ไม่พบ Zip: $ZIP_PATH"; exit 1; }

echo "⏬ Stopping & removing containers + named volumes…"
$COMPOSE down -v --remove-orphans || true

# ล้างโฟลเดอร์ bind‑mount เพิ่มเติม (ห้ามล้างที่เก็บ zip)
if [ -n "${BIND_DATA_DIRS:-}" ]; then
  IFS=',' read -ra DIRS <<< "$BIND_DATA_DIRS"
  for d in "${DIRS[@]}"; do
    d="$(echo "$d" | xargs)"
    [ -z "$d" ] && continue
    [[ "$d" = "/" || "$d" = "." ]] && { echo "❌ ปฏิเสธการล้าง '$d'"; exit 1; }
    mkdir -p "$d"
    echo "🧹 Wiping $d"
    find "$d" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  done
fi

echo "🔨 Build (ถ้าจำเป็น)…"
$COMPOSE build --pull

echo "🐬 Starting database…"
$COMPOSE up -d db

echo "⏳ Waiting for database to be healthy…"
# ใช้ container_name จาก compose: drugbank_db
for i in {1..60}; do
  status=$(docker inspect -f '{{.State.Health.Status}}' drugbank_db 2>/dev/null || echo "starting")
  if [ "$status" = "healthy" ]; then echo "✅ DB healthy"; break; fi
  sleep 2
done
if [ "${status:-}" != "healthy" ]; then
  echo "❌ DB ยังไม่ healthy"; $COMPOSE logs db; exit 1
fi

echo "🌱 Running loader (fresh import)…"
# ใช้ service 'loader' ตาม compose ให้รันจบหนึ่งรอบ
$COMPOSE run --rm loader

echo "🚀 Starting UIs & workspace…"
$COMPOSE up -d mywebsql dbgate mysql-workspace

echo "✅ Done. Fresh DrugBank loaded into '$DB_NAME'."
