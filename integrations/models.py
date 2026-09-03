from django.db import models


class AllDataLink(models.Model):
    """A manually-saved link to a page in the user's OWN ALLDATA subscription.

    This app never fetches, scrapes, or stores ALLDATA's content -- it just
    remembers a URL so a shop that already pays for ALLDATA can jump straight
    to the matching page for a vehicle, in their own logged-in browser tab.
    """

    vehicle = models.ForeignKey(
        "vehicles.Vehicle", on_delete=models.CASCADE, related_name="alldata_links"
    )
    label = models.CharField(max_length=150, help_text="e.g. 'Brake system diagram', 'TSB 21-045'")
    url = models.URLField(max_length=1000)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.label


class AllDataAttachment(models.Model):
    """A file the user exported/saved from their own ALLDATA account and is
    choosing to attach to a vehicle or work order for their own reference.

    Uploaded and owned entirely by the user -- Repair-Hub does not fetch this
    itself. Respect ALLDATA's terms of service for your subscription when
    deciding what you export and store here.
    """

    vehicle = models.ForeignKey(
        "vehicles.Vehicle", on_delete=models.CASCADE, related_name="alldata_attachments", null=True, blank=True
    )
    work_order = models.ForeignKey(
        "shop.WorkOrder", on_delete=models.CASCADE, related_name="alldata_attachments", null=True, blank=True
    )
    file = models.FileField(upload_to="alldata_attachments/%Y/%m/")
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.description or self.file.name
