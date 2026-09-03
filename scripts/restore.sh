#!/bin/sh
# Restore a Repair-Hub backup created by backup.sh.
# Usage: ./scripts/restore.sh backups/repairhub-20260101-030000.tar.gz [container-name]
#
# WARNING: this REPLACES the database and media in the running container.
# Stops the container first so nothing writes mid-restore.
set -e

BACKUP_FILE="$1"
CONTAINER="${2:-repair-hub}"

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: $0 <path-to-backup.tar.gz> [container-name]"
  exit 1
fi

echo "This will REPLACE the database and media inside container '${CONTAINER}'."
printf "Type 'yes' to continue: "
read -r CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

echo "Stopping ${CONTAINER}..."
docker stop "$CONTAINER"

echo "Restoring ${BACKUP_FILE}..."
docker run --rm --volumes-from "$CONTAINER" -v "$(cd "$(dirname "$BACKUP_FILE")" && pwd):/restore" alpine \
  sh -c "rm -rf /config/media && tar xzf /restore/$(basename "$BACKUP_FILE") -C /config && mv /config/db.sqlite3.bak /config/db.sqlite3"

echo "Starting ${CONTAINER}..."
docker start "$CONTAINER"

echo "Restore complete."
