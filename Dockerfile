FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/config/db.sqlite3 \
    MEDIA_ROOT=/config/media \
    BACKUP_DIR=/config/backups

WORKDIR /app

# gosu drops from root to the PUID/PGID user in entrypoint.sh, matching
# Unraid's convention of appdata owned by a specific uid/gid (default 99:100).
# sqlite3 is the CLI used by scripts/backup.sh for safe hot backups.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

RUN mkdir -p /config/media /app/staticfiles

VOLUME /config
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/login/', timeout=3)" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
