#!/bin/sh
set -e

PUID="${PUID:-99}"
PGID="${PGID:-100}"

mkdir -p /config/media

if [ "$(id -u)" = "0" ]; then
  groupmod -o -g "$PGID" appgroup 2>/dev/null || groupadd -o -g "$PGID" appgroup
  usermod -o -u "$PUID" appuser 2>/dev/null || useradd -o -u "$PUID" -g "$PGID" -M -s /usr/sbin/nologin -K UID_MIN=1 -K UID_MAX=65535 appuser
  chown -R "$PUID:$PGID" /config /app/staticfiles

  export DJANGO_SUPERUSER_USERNAME DJANGO_SUPERUSER_EMAIL DJANGO_SUPERUSER_PASSWORD \
    DJANGO_SECRET_KEY DJANGO_DEBUG DJANGO_ALLOWED_HOSTS DB_PATH MEDIA_ROOT DJANGO_TIME_ZONE TZ
  exec gosu "$PUID:$PGID" "$0" "$@"
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py seed_dtc_codes

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
username = '$DJANGO_SUPERUSER_USERNAME'
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')
    print(f'Created superuser {username}')
else:
    print(f'Superuser {username} already exists')
"
fi

exec gunicorn repairhub.wsgi:application --bind 0.0.0.0:8000 --workers 3
