import io

import qrcode
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from diagnostics.models import DTCCode
from repairguides.models import RepairGuide
from shop.models import Appointment, Customer, Estimate, InventoryPart, WorkOrder
from vehicles.models import MaintenanceReminder, Vehicle

from .backup import BACKUP_APPS
from .decorators import staff_required
from .models import Favorite, TwoFactorCredential


@login_required
def dashboard(request):
    customer = getattr(request.user, "customer_profile", None)
    if customer is not None:
        return redirect("shop:customer_dashboard")
    technician = getattr(request.user, "technician_profile", None)
    if technician is not None:
        return redirect("shop:technician_dashboard")

    reminders_due = [r for r in MaintenanceReminder.objects.filter(completed=False).select_related(
        "vehicle", "vehicle__make", "vehicle__model"
    ) if r.is_due_soon][:10]

    vehicles_with_recalls = Vehicle.objects.filter(open_recall_count__gt=0).select_related(
        "make", "model", "owner"
    )[:10]

    low_stock_parts = [p for p in InventoryPart.objects.all() if p.is_low_stock][:10]

    context = {
        "vehicle_count": Vehicle.objects.count(),
        "guide_count": RepairGuide.objects.count(),
        "dtc_count": DTCCode.objects.count(),
        "customer_count": Customer.objects.count(),
        "open_work_orders": WorkOrder.objects.exclude(status__in=["closed", "invoiced"]).select_related(
            "customer", "vehicle"
        )[:10],
        "pending_estimates": Estimate.objects.filter(status="sent").select_related("customer", "vehicle")[:10],
        "upcoming_appointments": Appointment.objects.filter(
            scheduled_at__gte=timezone.now(), status__in=["scheduled", "confirmed"]
        ).select_related("customer", "vehicle")[:10],
        "reminders_due": reminders_due,
        "vehicles_with_recalls": vehicles_with_recalls,
        "low_stock_parts": low_stock_parts,
    }
    return render(request, "core/dashboard.html", context)


@login_required
def toggle_favorite(request):
    if request.method == "POST":
        content_type = get_object_or_404(ContentType, pk=request.POST.get("content_type_id"))
        object_id = request.POST.get("object_id")
        favorite, created = Favorite.objects.get_or_create(
            user=request.user, content_type=content_type, object_id=object_id
        )
        if not created:
            favorite.delete()
    next_url = request.POST.get("next") or reverse("dashboard")
    return redirect(next_url)


@staff_required
def favorites_list(request):
    favorites = Favorite.objects.filter(user=request.user).select_related("content_type")
    items = [f for f in favorites if f.content_object is not None]
    return render(request, "core/favorites.html", {"items": items})


@staff_required
def global_search(request):
    query = request.GET.get("q", "").strip()
    results = {"vehicles": [], "guides": [], "dtc_codes": [], "customers": [], "work_orders": []}
    if query:
        results["vehicles"] = list(
            Vehicle.objects.filter(vin__icontains=query) | Vehicle.objects.filter(make__name__icontains=query)
            | Vehicle.objects.filter(model__name__icontains=query)
        )[:20]
        results["guides"] = list(RepairGuide.objects.filter(title__icontains=query))[:20]
        results["dtc_codes"] = list(
            DTCCode.objects.filter(code__icontains=query) | DTCCode.objects.filter(description__icontains=query)
        )[:20]
        results["customers"] = list(Customer.objects.filter(name__icontains=query))[:20]
        results["work_orders"] = list(
            WorkOrder.objects.filter(complaint__icontains=query).select_related("customer", "vehicle")
        )[:20]
    return render(request, "core/search_results.html", {"query": query, "results": results})


@staff_required
def download_backup(request):
    """Download a JSON snapshot of business data (vehicles, guides, DTC
    codes, shop records, favorites, and staff/customer accounts). Uploaded
    files (photos, diagrams, attachments) are NOT included -- back up the
    media volume separately. This is a convenience export, not a substitute
    for a real Postgres backup (see README)."""
    buffer = io.StringIO()
    call_command("dumpdata", *BACKUP_APPS, indent=2, stdout=buffer)
    filename = f"repairhub-backup-{timezone.now():%Y%m%d-%H%M%S}.json"
    response = HttpResponse(buffer.getvalue(), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class TwoFactorLoginView(LoginView):
    """Same as Django's LoginView, except a user with 2FA enabled gets sent
    to a code-verification step instead of being logged in immediately."""

    template_name = "registration/login.html"

    def form_valid(self, form):
        user = form.get_user()
        credential = getattr(user, "two_factor", None)
        if credential and credential.enabled:
            self.request.session["2fa_user_id"] = user.pk
            self.request.session["2fa_next"] = self.get_success_url()
            return redirect("two_factor_verify")
        return super().form_valid(form)


def two_factor_verify(request):
    """Second login step for accounts with 2FA enabled. Deliberately not
    @login_required -- the user isn't logged in yet at this point."""
    user_id = request.session.get("2fa_user_id")
    if not user_id:
        return redirect("login")
    if request.session.get("2fa_attempts", 0) >= 5:
        request.session.pop("2fa_user_id", None)
        request.session.pop("2fa_attempts", None)
        messages.error(request, "Too many attempts. Please log in again.")
        return redirect("login")
    user = get_object_or_404(get_user_model(), pk=user_id)
    error = None
    if request.method == "POST":
        credential = getattr(user, "two_factor", None)
        if credential and credential.enabled and credential.verify(request.POST.get("code", "").strip()):
            request.session.pop("2fa_user_id", None)
            request.session.pop("2fa_attempts", None)
            next_url = request.session.pop("2fa_next", None) or reverse("dashboard")
            auth_login(request, user)
            return redirect(next_url)
        request.session["2fa_attempts"] = request.session.get("2fa_attempts", 0) + 1
        error = "Invalid code."
    return render(request, "registration/two_factor_verify.html", {"error": error})


@staff_required
def two_factor_setup(request):
    credential, _ = TwoFactorCredential.objects.get_or_create(user=request.user)
    if request.method == "POST" and not credential.enabled:
        if credential.verify(request.POST.get("code", "").strip()):
            credential.enabled = True
            credential.confirmed_at = timezone.now()
            credential.save(update_fields=["enabled", "confirmed_at"])
            messages.success(request, "Two-factor authentication is now enabled on your account.")
            return redirect("two_factor_setup")
        messages.error(request, "That code didn't match. Scan the QR code again and try the current one.")
    return render(request, "registration/two_factor_setup.html", {"credential": credential})


@staff_required
def two_factor_qr_code(request):
    credential = get_object_or_404(TwoFactorCredential, user=request.user, enabled=False)
    img = qrcode.make(credential.provisioning_uri())
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")


@staff_required
def two_factor_disable(request):
    if request.method == "POST":
        TwoFactorCredential.objects.filter(user=request.user).delete()
        messages.success(request, "Two-factor authentication disabled.")
    return redirect("two_factor_setup")
