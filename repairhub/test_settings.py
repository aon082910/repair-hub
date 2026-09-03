"""Settings for running the test suite -- swaps Postgres for an in-memory
SQLite database so tests run without needing a Postgres server (locally or
in CI). Usage: python manage.py test --settings=repairhub.test_settings
"""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-suite-secret-key")

from .settings import *  # noqa: E402,F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
