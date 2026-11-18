#!/bin/sh
set -e
mkdir -p "$DATA_DIR"
python -m app.cli init-db
python -m app.cli seed-techniques
exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8080 \
  --proxy-headers --forwarded-allow-ips='*'
