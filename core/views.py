import io

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from diagnostics.models import DTCCode
from repairguides.models import RepairGuide
from shop.models import Appointment, Customer, Estimate, WorkOrder
from vehicles.models import MaintenanceReminder, Vehicle

from .decorators import staff_required
from .models import Favorite


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
    call_command(
        "dumpdata",
        "auth.User",
        "vehicles",
        "diagnostics",
        "repairguides",
        "shop",
        "integrations",
        "core.Favorite",
        indent=2,
        stdout=buffer,
    )
    filename = f"repairhub-backup-{timezone.now():%Y%m%d-%H%M%S}.json"
    response = HttpResponse(buffer.getvalue(), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
