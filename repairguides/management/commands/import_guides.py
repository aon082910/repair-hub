"""Bulk-import repair guides from a JSON file.

Usage:
    python manage.py import_guides path/to/guides.json

Expected JSON shape -- a list of guide objects:
[
  {
    "title": "Front brake pad replacement",
    "system": "Brakes",
    "make": "Honda",
    "model": "Civic",
    "year_start": 2016,
    "year_end": 2021,
    "vin": "",
    "summary": "Replace worn front pads and inspect rotors.",
    "dtc_codes": ["P0420"],
    "steps": [
      {"order": 1, "instructions": "Loosen lug nuts, raise and support the vehicle.", "torque_spec": "", "caution": ""},
      {"order": 2, "instructions": "Remove caliper bolts, torque to spec on reinstall.", "torque_spec": "27 ft-lb", "caution": "Do not let caliper hang by the brake hose."}
    ]
  }
]

This is meant for importing YOUR OWN content (guides you've written, or
notes/exports from your own paid ALLDATA subscription for your own vehicles)
-- it does not fetch or scrape anything. The same logic backs the web-based
importer at /guides/import/.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from ...importers import GuideImportError, import_guides_from_records


class Command(BaseCommand):
    help = "Bulk import repair guides from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str)
        parser.add_argument(
            "--update",
            action="store_true",
            help="If a guide with the same title+system already exists, update it instead of skipping.",
        )

    def handle(self, *args, **options):
        path = options["json_path"]
        try:
            with open(path, encoding="utf-8") as f:
                records = json.load(f)
        except FileNotFoundError as exc:
            raise CommandError(f"File not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {path}: {exc}") from exc

        try:
            stats = import_guides_from_records(records, update=options["update"])
        except GuideImportError as exc:
            raise CommandError(str(exc)) from exc

        for msg in stats["skipped"]:
            self.stderr.write(self.style.WARNING(msg))

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {stats['created']} created, {stats['updated']} updated, "
                f"{len(stats['skipped'])} skipped."
            )
        )
