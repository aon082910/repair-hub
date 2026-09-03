import datetime
import uuid
from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.utils import timezone


class ShopSettings(models.Model):
    """Singleton: shop-wide settings that apply to every invoice/estimate."""

    tax_rate_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text="Sales tax rate applied to labor + parts, e.g. 8.25 for 8.25%.",
    )
    business_name = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name_plural = "shop settings"

    def __str__(self):
        return "Shop Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Customer(models.Model):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    tax_exempt = models.BooleanField(default=False, help_text="e.g. resale/wholesale customers")
    user = models.OneToOneField(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_profile",
        help_text="Linked login this customer can use to view their own vehicles/work orders.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("shop:customer_detail", args=[self.pk])


class Technician(models.Model):
    """A technician account: narrower access than staff -- reference lookup
    (vehicles/guides/DTC/wiring) plus their own assigned work orders only."""

    user = models.OneToOneField(
        "auth.User", on_delete=models.CASCADE, related_name="technician_profile"
    )
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class WorkOrder(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("waiting_parts", "Waiting on Parts"),
        ("completed", "Completed"),
        ("invoiced", "Invoiced"),
        ("closed", "Closed"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="work_orders")
    vehicle = models.ForeignKey(
        "vehicles.Vehicle", on_delete=models.CASCADE, related_name="work_orders"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    odometer = models.PositiveIntegerField(null=True, blank=True)
    complaint = models.TextField(help_text="Customer's reported issue / requested work.")
    diagnosis_notes = models.TextField(blank=True)
    assigned_technician = models.ForeignKey(
        Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name="work_orders"
    )
    repair_guides = models.ManyToManyField(
        "repairguides.RepairGuide", blank=True, related_name="work_orders"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    access_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    warranty_months = models.PositiveIntegerField(
        null=True, blank=True, help_text="Parts/labor warranty on this repair, in months from completion."
    )
    warranty_miles = models.PositiveIntegerField(
        null=True, blank=True, help_text="Warranty mileage limit from the odometer reading at completion."
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"WO#{self.pk} - {self.vehicle} ({self.customer})"

    def get_absolute_url(self):
        return reverse("shop:workorder_detail", args=[self.pk])

    def get_portal_url(self):
        return reverse("shop:customer_portal", args=[self.access_token])

    @property
    def labor_total(self) -> Decimal:
        total = Decimal("0.00")
        for line in self.labor_lines.all():
            total += line.hours * line.rate
        return total

    @property
    def parts_total(self) -> Decimal:
        total = Decimal("0.00")
        for line in self.part_lines.all():
            total += line.quantity * line.unit_price
        return total

    @property
    def tax_total(self) -> Decimal:
        if self.customer.tax_exempt:
            return Decimal("0.00")
        rate = ShopSettings.get_solo().tax_rate_percent
        return (self.labor_total + self.parts_total) * rate / Decimal("100")

    @property
    def grand_total(self) -> Decimal:
        return self.labor_total + self.parts_total + self.tax_total

    @property
    def warranty_expiration_date(self):
        if self.warranty_months and self.completed_at:
            return (self.completed_at + datetime.timedelta(days=30 * self.warranty_months)).date()
        return None

    @property
    def is_under_warranty(self) -> bool:
        expiration = self.warranty_expiration_date
        if expiration is None:
            return False
        if timezone.localdate() > expiration:
            return False
        if self.warranty_miles and self.odometer is not None:
            current = self.vehicle.latest_odometer()
            if current is not None and (current - self.odometer) > self.warranty_miles:
                return False
        return True


class LaborLine(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="labor_lines")
    description = models.CharField(max_length=255)
    hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    rate = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return self.description

    @property
    def line_total(self) -> Decimal:
        return self.hours * self.rate


class InventoryPart(models.Model):
    part_number = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255)
    quantity_on_hand = models.IntegerField(default=0)
    reorder_point = models.IntegerField(default=0, help_text="Flag as low stock at or below this quantity.")
    unit_cost = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    default_price = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00"), help_text="What you typically charge for this part."
    )
    location = models.CharField(max_length=100, blank=True, help_text="Shelf/bin location.")

    class Meta:
        ordering = ["part_number"]

    def __str__(self):
        return f"{self.part_number} - {self.description}"

    @property
    def is_low_stock(self) -> bool:
        return self.quantity_on_hand <= self.reorder_point


class PartLine(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="part_lines")
    inventory_part = models.ForeignKey(
        InventoryPart, on_delete=models.SET_NULL, null=True, blank=True, related_name="part_lines"
    )
    part_number = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return self.description

    @property
    def line_total(self) -> Decimal:
        return self.quantity * self.unit_price


class Estimate(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent to Customer"),
        ("approved", "Approved"),
        ("declined", "Declined"),
        ("converted", "Converted to Work Order"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="estimates")
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.CASCADE, related_name="estimates")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    notes = models.TextField(blank=True, help_text="What this estimate covers.")
    access_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    signature_data = models.TextField(
        blank=True, help_text="Base64 PNG data URI captured from the customer's approval signature."
    )
    work_order = models.OneToOneField(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="estimate"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Estimate #{self.pk} - {self.vehicle} ({self.customer})"

    def get_absolute_url(self):
        return reverse("shop:estimate_detail", args=[self.pk])

    def get_portal_url(self):
        return reverse("shop:estimate_portal", args=[self.access_token])

    @property
    def labor_total(self) -> Decimal:
        return sum((line.line_total for line in self.labor_lines.all()), Decimal("0.00"))

    @property
    def parts_total(self) -> Decimal:
        return sum((line.line_total for line in self.part_lines.all()), Decimal("0.00"))

    @property
    def tax_total(self) -> Decimal:
        if self.customer.tax_exempt:
            return Decimal("0.00")
        rate = ShopSettings.get_solo().tax_rate_percent
        return (self.labor_total + self.parts_total) * rate / Decimal("100")

    @property
    def grand_total(self) -> Decimal:
        return self.labor_total + self.parts_total + self.tax_total


class EstimateLaborLine(models.Model):
    estimate = models.ForeignKey(Estimate, on_delete=models.CASCADE, related_name="labor_lines")
    description = models.CharField(max_length=255)
    hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    rate = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return self.description

    @property
    def line_total(self) -> Decimal:
        return self.hours * self.rate


class EstimatePartLine(models.Model):
    estimate = models.ForeignKey(Estimate, on_delete=models.CASCADE, related_name="part_lines")
    part_number = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return self.description

    @property
    def line_total(self) -> Decimal:
        return self.quantity * self.unit_price


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("confirmed", "Confirmed"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("no_show", "No-Show"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="appointments")
    vehicle = models.ForeignKey(
        "vehicles.Vehicle", on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments"
    )
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=60)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.scheduled_at:%Y-%m-%d %H:%M} - {self.customer} ({self.reason})"

    def get_absolute_url(self):
        return reverse("shop:appointment_detail", args=[self.pk])


class Invoice(models.Model):
    work_order = models.OneToOneField(WorkOrder, on_delete=models.CASCADE, related_name="invoice")
    invoice_number = models.CharField(max_length=50, unique=True)
    issued_date = models.DateField(auto_now_add=True)
    paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.invoice_number

    @property
    def amount_paid(self) -> Decimal:
        return sum((p.amount for p in self.payments.all()), Decimal("0.00"))

    @property
    def balance_due(self) -> Decimal:
        return self.work_order.grand_total - self.amount_paid

    @property
    def is_fully_paid(self) -> bool:
        return self.balance_due <= Decimal("0.00")


class PaymentRecord(models.Model):
    METHOD_CHOICES = [
        ("cash", "Cash"),
        ("card", "Card"),
        ("check", "Check"),
        ("other", "Other"),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default="card")
    paid_date = models.DateField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-paid_date", "-id"]

    def __str__(self):
        return f"${self.amount} ({self.get_method_display()})"


class TimeEntry(models.Model):
    """A technician's clocked time against one work order."""

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="time_entries")
    technician = models.ForeignKey(Technician, on_delete=models.CASCADE, related_name="time_entries")
    clock_in = models.DateTimeField(auto_now_add=True)
    clock_out = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-clock_in"]

    def __str__(self):
        return f"{self.technician} on WO#{self.work_order_id}"

    @property
    def is_active(self) -> bool:
        return self.clock_out is None

    @property
    def duration_hours(self) -> Decimal:
        end = self.clock_out or timezone.now()
        seconds = (end - self.clock_in).total_seconds()
        return Decimal(seconds / 3600).quantize(Decimal("0.01"))


DEFAULT_INSPECTION_ITEMS = [
    ("Brakes", "Front pads/rotors"),
    ("Brakes", "Rear pads/rotors"),
    ("Tires", "Tread depth / wear pattern"),
    ("Tires", "Tire pressure"),
    ("Fluids", "Engine oil level/condition"),
    ("Fluids", "Coolant level"),
    ("Fluids", "Brake fluid"),
    ("Battery", "Battery condition/terminals"),
    ("Lights", "Headlights/taillights/signals"),
    ("Wipers", "Wiper blades"),
    ("Belts & Hoses", "Serpentine belt"),
    ("Belts & Hoses", "Visible hoses"),
    ("Suspension", "Shocks/struts"),
    ("Exhaust", "Exhaust system condition"),
]


class Inspection(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="inspections")
    technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True)
    access_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Inspection #{self.pk} - {self.work_order.vehicle}"

    def get_absolute_url(self):
        return reverse("shop:inspection_detail", args=[self.pk])

    def get_portal_url(self):
        return reverse("shop:inspection_portal", args=[self.access_token])

    def create_default_items(self):
        InspectionItem.objects.bulk_create(
            [
                InspectionItem(inspection=self, category=cat, description=desc)
                for cat, desc in DEFAULT_INSPECTION_ITEMS
            ]
        )


class InspectionItem(models.Model):
    STATUS_CHOICES = [
        ("green", "Good"),
        ("yellow", "Monitor"),
        ("red", "Needs Attention"),
    ]

    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="items")
    category = models.CharField(max_length=100)
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="green")
    notes = models.TextField(blank=True)
    photo = models.ImageField(upload_to="inspection_photos/%Y/%m/", null=True, blank=True)

    class Meta:
        ordering = ["category", "id"]

    def __str__(self):
        return f"{self.category}: {self.description}"


class ActivityLogEntry(models.Model):
    """A lightweight audit trail for the events that matter most: work order
    and estimate status changes, and account creation. Not every field
    change is tracked -- this is a status/who-did-what log, not full
    field-level history."""

    user = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    object_repr = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name_plural = "activity log entries"

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} — {self.action}"
