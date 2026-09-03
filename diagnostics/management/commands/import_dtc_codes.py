"""Bulk-import DTC codes from a CSV file.

Usage:
    python manage.py import_dtc_codes path/to/codes.csv

Expected CSV columns (header row required):
    code,description,system,origin,make,likely_causes,diagnostic_steps

- system: one of P, B, C, U (auto-derived from the code's first letter if blank)
- origin: "generic" or "manufacturer" (defaults to "manufacturer" if a make is given)
- make: only needed for manufacturer-specific codes

The same logic backs the web-based importer at /diagnostics/import/.
"""
from django.core.management.base import BaseCommand, CommandError

from ...importers import DTCImportError, import_dtc_codes_from_csv


class Command(BaseCommand):
    help = "Bulk import DTC codes from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)

    def handle(self, *args, **options):
        path = options["csv_path"]
        try:
            f = open(path, newline="", encoding="utf-8-sig")
        except FileNotFoundError as exc:
            raise CommandError(f"File not found: {path}") from exc

        with f:
            try:
                stats = import_dtc_codes_from_csv(f)
            except DTCImportError as exc:
                raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Import complete: {stats['created']} created, {stats['updated']} updated.")
        )
