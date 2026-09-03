from django.db import models
from django.urls import reverse


class System(models.Model):
    """Repair category, e.g. Engine, Brakes, Electrical, HVAC, Transmission."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "systems"

    def __str__(self):
        return self.name


class RepairGuide(models.Model):
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.CASCADE,
        related_name="repair_guides",
        null=True,
        blank=True,
        help_text="Specific vehicle this guide applies to (optional if generic).",
    )
    make = models.ForeignKey(
        "vehicles.Make",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Use instead of a specific vehicle for guides that apply to a whole make/model range.",
    )
    model = models.ForeignKey(
        "vehicles.VehicleModel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    year_start = models.PositiveIntegerField(null=True, blank=True)
    year_end = models.PositiveIntegerField(null=True, blank=True)

    system = models.ForeignKey(System, on_delete=models.PROTECT, related_name="guides")
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    dtc_codes = models.ManyToManyField("diagnostics.DTCCode", blank=True, related_name="guides")
    author = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="repair_guides"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("repairguides:detail", args=[self.pk])


class GuideStep(models.Model):
    guide = models.ForeignKey(RepairGuide, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveIntegerField(default=1)
    instructions = models.TextField()
    torque_spec = models.CharField(max_length=100, blank=True)
    caution = models.TextField(blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Step {self.order}: {self.guide.title}"


class GuideImage(models.Model):
    guide = models.ForeignKey(RepairGuide, on_delete=models.CASCADE, related_name="images")
    step = models.ForeignKey(
        GuideStep, on_delete=models.CASCADE, related_name="images", null=True, blank=True
    )
    image = models.ImageField(upload_to="guide_images/%Y/%m/")
    caption = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.caption or f"Image for {self.guide.title}"


class WiringDiagram(models.Model):
    vehicle = models.ForeignKey(
        "vehicles.Vehicle", on_delete=models.CASCADE, related_name="wiring_diagrams", null=True, blank=True
    )
    make = models.ForeignKey("vehicles.Make", on_delete=models.SET_NULL, null=True, blank=True)
    model = models.ForeignKey("vehicles.VehicleModel", on_delete=models.SET_NULL, null=True, blank=True)
    year_start = models.PositiveIntegerField(null=True, blank=True)
    year_end = models.PositiveIntegerField(null=True, blank=True)
    system = models.ForeignKey(System, on_delete=models.PROTECT, related_name="wiring_diagrams")
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="wiring_diagrams/%Y/%m/")
    description = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title
