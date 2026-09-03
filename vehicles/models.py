import datetime
import uuid

from django.db import models
from django.urls import reverse
from django.utils import timezone


class Make(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class VehicleModel(models.Model):
    make = models.ForeignKey(Make, on_delete=models.CASCADE, related_name="models")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["make__name", "name"]
        unique_together = ("make", "name")

    def __str__(self):
        return f"{self.make.name} {self.name}"


class Vehicle(models.Model):
    """A specific vehicle: either a customer's real vehicle or a reference
    entry (e.g. '2016 Honda Civic') that repair guides can be attached to."""

    year = models.PositiveIntegerField()
    make = models.ForeignKey(Make, on_delete=models.PROTECT, related_name="vehicles")
    model = models.ForeignKey(VehicleModel, on_delete=models.PROTECT, related_name="vehicles")
    trim = models.CharField(max_length=100, blank=True)
    engine = models.CharField(max_length=100, blank=True)
    vin = models.CharField(max_length=17, blank=True, db_index=True)
    owner = models.ForeignKey(
        "shop.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicles",
        help_text="Leave blank for a reference-only vehicle entry.",
    )
    notes = models.TextField(blank=True)
    access_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "make__name", "model__name"]

    def __str__(self):
        trim = f" {self.trim}" if self.trim else ""
        return f"{self.year} {self.make.name} {self.model.name}{trim}"

    def get_service_history_url(self):
        return reverse("vehicles:service_history", args=[self.access_token])

    def get_absolute_url(self):
        return reverse("vehicles:detail", args=[self.pk])

    def latest_odometer(self):
        reading = self.work_orders.exclude(odometer__isnull=True).order_by("-odometer").values_list(
            "odometer", flat=True
        ).first()
        return reading


class MaintenanceReminder(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="maintenance_reminders")
    description = models.CharField(max_length=255, help_text="e.g. Oil change, Timing belt")
    due_date = models.DateField(null=True, blank=True)
    due_mileage = models.PositiveIntegerField(null=True, blank=True)
    interval_months = models.PositiveIntegerField(
        null=True, blank=True, help_text="If set, a new reminder is auto-created this many months out when marked done."
    )
    interval_miles = models.PositiveIntegerField(
        null=True, blank=True, help_text="If set, a new reminder is auto-created this many miles out when marked done."
    )
    notes = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "due_mileage"]

    def __str__(self):
        return f"{self.description} - {self.vehicle}"

    @property
    def is_due_soon(self) -> bool:
        if self.completed:
            return False
        if self.due_date and self.due_date <= timezone.localdate() + datetime.timedelta(days=30):
            return True
        if self.due_mileage:
            current = self.vehicle.latest_odometer()
            if current is not None and self.due_mileage - current <= 1000:
                return True
        return False

    @property
    def is_overdue(self) -> bool:
        if self.completed:
            return False
        if self.due_date and self.due_date < timezone.localdate():
            return True
        if self.due_mileage:
            current = self.vehicle.latest_odometer()
            if current is not None and current >= self.due_mileage:
                return True
        return False

    def mark_done(self):
        self.completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=["completed", "completed_at"])

        if self.interval_months or self.interval_miles:
            next_due_date = None
            next_due_mileage = None
            if self.interval_months:
                base_date = self.due_date or timezone.localdate()
                next_due_date = base_date + datetime.timedelta(days=30 * self.interval_months)
            if self.interval_miles:
                base_mileage = self.vehicle.latest_odometer() or self.due_mileage or 0
                next_due_mileage = base_mileage + self.interval_miles
            MaintenanceReminder.objects.create(
                vehicle=self.vehicle,
                description=self.description,
                due_date=next_due_date,
                due_mileage=next_due_mileage,
                interval_months=self.interval_months,
                interval_miles=self.interval_miles,
            )
