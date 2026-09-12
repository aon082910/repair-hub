import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from vehicles.models import Vehicle


class Command(BaseCommand):
    help = (
        "Refresh cached NHTSA open-recall counts for customer-owned vehicles, "
        "so the staff dashboard can flag them without a live API call per page load."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true", help="Re-check even vehicles checked within the last 7 days."
        )
        parser.add_argument(
            "--delay", type=float, default=0.3, help="Seconds to sleep between API calls (be polite to NHTSA)."
        )

    def handle(self, *args, **options):
        vehicles = Vehicle.objects.filter(owner__isnull=False).select_related("make", "model")
        if not options["force"]:
            cutoff = timezone.now() - timezone.timedelta(days=7)
            vehicles = vehicles.filter(recalls_checked_at__isnull=True) | vehicles.filter(
                recalls_checked_at__lt=cutoff
            )

        checked = 0
        flagged = 0
        for vehicle in vehicles:
            recalls = vehicle.refresh_recalls()
            checked += 1
            if recalls:
                flagged += 1
            time.sleep(options["delay"])

        self.stdout.write(
            self.style.SUCCESS(f"Checked {checked} vehicle(s); {flagged} have at least one open recall.")
        )
