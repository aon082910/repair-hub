#!/bin/sh
# Back up the Repair-Hub SQLite database (via a safe hot .backup, not a raw
# file copy) plus all uploaded media into one timestamped tarball in
# ./backups/. Run against the running container by name, e.g. via an Unraid
# User Scripts cron job:
#   ./scripts/backup.sh repair-hub
set -e

CONTAINER="${1:-repair-hub}"
cd "$(dirname "$0")/.."
mkdir -p backups

STAMP=$(date +%Y%m%d-%H%M%S)
OUT="backups/repairhub-${STAMP}.tar.gz"

echo "Snapshotting database inside ${CONTAINER}..."
docker exec "$CONTAINER" sqlite3 /config/db.sqlite3 ".backup /config/db.sqlite3.bak"

echo "Archiving /config to ${OUT}..."
docker run --rm --volumes-from "$CONTAINER" -v "$(pwd)/backups:/backups" alpine \
  tar czf "/backups/repairhub-${STAMP}.tar.gz" -C /config db.sqlite3.bak media

docker exec "$CONTAINER" rm -f /config/db.sqlite3.bak

echo "Done: $OUT"

# Keep the last 14 backups, delete older ones.
ls -1t backups/repairhub-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm --
