import pyotp
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Favorite(models.Model):
    """A user's bookmark on any object (repair guide, DTC code, vehicle, ...)."""

    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="favorites")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "content_type", "object_id")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} ★ {self.content_object}"


class TwoFactorCredential(models.Model):
    """Optional TOTP-based 2FA for a staff login. A row with enabled=False
    is a secret generated during setup but not yet confirmed with a code --
    it doesn't affect login until confirmed."""

    user = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="two_factor")
    secret = models.CharField(max_length=32, default=pyotp.random_base32)
    enabled = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"2FA for {self.user}"

    def verify(self, code: str) -> bool:
        return pyotp.TOTP(self.secret).verify(code, valid_window=1)

    def provisioning_uri(self) -> str:
        return pyotp.TOTP(self.secret).provisioning_uri(name=self.user.username, issuer_name="Repair-Hub")
