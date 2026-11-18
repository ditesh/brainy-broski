#!/bin/sh
# Make a dated copy of the database on the server, then download it.
# Usage: scripts/backup.sh [local-dir]
set -e
DEST="${1:-./backups}"
mkdir -p "$DEST"
fly ssh console -C "python -m app.cli backup"
FILE="app-$(date +%F).db"
fly ssh sftp get "/data/backups/$FILE" "$DEST/$FILE"
echo "Saved $DEST/$FILE"
