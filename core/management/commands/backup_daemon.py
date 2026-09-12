import os
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Run backup_snapshot on a repeating interval. Intended to run as a "
        "single long-lived background process (started once from entrypoint.sh, "
        "not per gunicorn worker). Set BACKUP_INTERVAL_HOURS=0 to disable."
    )

    def handle(self, *args, **options):
        try:
            interval_hours = float(os.environ.get("BACKUP_INTERVAL_HOURS", "24"))
        except ValueError:
            interval_hours = 24

        if interval_hours <= 0:
            self.stdout.write("BACKUP_INTERVAL_HOURS is 0 -- scheduled backups disabled.")
            return

        interval_seconds = interval_hours * 3600
        self.stdout.write(f"Scheduled backups every {interval_hours} hour(s).")
        while True:
            try:
                call_command("backup_snapshot")
            except Exception as exc:  # noqa: BLE001 -- a bad backup run must never kill the daemon
                self.stderr.write(f"backup_snapshot failed: {exc}")
            time.sleep(interval_seconds)
