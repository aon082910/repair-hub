import os
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.backup import BACKUP_APPS


class Command(BaseCommand):
    help = (
        "Write a timestamped JSON snapshot of business data to /config/backups "
        "and prune old snapshots beyond the retention count. Does not include "
        "uploaded media -- back up the /config volume itself for that."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--out-dir",
            default=os.environ.get("BACKUP_DIR", str(Path(settings.BASE_DIR) / "config" / "backups")),
        )
        parser.add_argument(
            "--retention", type=int, default=int(os.environ.get("BACKUP_RETENTION_COUNT", "14"))
        )

    def handle(self, *args, **options):
        out_dir = Path(options["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"repairhub-backup-{timezone.now():%Y%m%d-%H%M%S-%f}.json"
        path = out_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            call_command("dumpdata", *BACKUP_APPS, indent=2, stdout=f)

        retention = max(options["retention"], 1)
        existing = sorted(out_dir.glob("repairhub-backup-*.json"))
        for old_path in existing[:-retention]:
            old_path.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS(f"Wrote {path} (keeping the {retention} most recent)."))
