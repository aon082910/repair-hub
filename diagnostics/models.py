from django.db import models


class DTCCode(models.Model):
    SYSTEM_CHOICES = [
        ("P", "Powertrain"),
        ("B", "Body"),
        ("C", "Chassis"),
        ("U", "Network/Communication"),
    ]
    ORIGIN_CHOICES = [
        ("generic", "Generic (SAE standard, applies across manufacturers)"),
        ("manufacturer", "Manufacturer-specific"),
    ]

    code = models.CharField(max_length=10, unique=True, db_index=True)
    system = models.CharField(max_length=1, choices=SYSTEM_CHOICES)
    origin = models.CharField(max_length=15, choices=ORIGIN_CHOICES, default="generic")
    make = models.ForeignKey(
        "vehicles.Make",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Only set for manufacturer-specific codes.",
    )
    description = models.CharField(max_length=255)
    likely_causes = models.TextField(blank=True)
    diagnostic_steps = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.description}"
