import csv
import datetime
import io
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from core.decorators import staff_or_technician_required, staff_required
from vehicles.models import Vehicle

from .models import (
    ActivityLogEntry,
    Appointment,
    Customer,
    Estimate,
    EstimateLaborLine,
    EstimatePartLine,
    Inspection,
    InspectionItem,
    Invoice,
    InventoryPart,
    LaborLine,
    PartLine,
    PaymentRecord,
    ShopSettings,
    Technician,
    TimeEntry,
    WorkOrder,
)
from .ics import build_appointments_ics
from .notifications import notify_appointment_created, notify_estimate_sent, notify_invoice_created
from .utils import log_activity


def _can_touch_work_order(request, work_order):
    if request.user.is_staff:
        return True
    tech = getattr(request.user, "technician_profile", None)
    return tech is not None and work_order.assigned_technician_id == tech.pk


@staff_required
def customer_list(request):
    query = request.GET.get("q", "").strip()
    customers = Customer.objects.all()
    if query:
        customers = customers.filter(name__icontains=query)
    return render(request, "shop/customer_list.html", {"customers": customers[:200], "query": query})


@staff_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    vehicles = customer.vehicles.all()
    work_orders = customer.work_orders.select_related("vehicle")
    return render(
        request,
        "shop/customer_detail.html",
        {"customer": customer, "vehicles": vehicles, "work_orders": work_orders},
    )


@staff_required
def customer_create(request):
    if request.method == "POST":
        customer = Customer.objects.create(
            name=request.POST.get("name", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            email=request.POST.get("email", "").strip(),
            address=request.POST.get("address", "").strip(),
        )
        log_activity(request.user, "Created customer", customer)
        return redirect(customer.get_absolute_url())
    return render(request, "shop/customer_form.html")


@staff_required
def customer_toggle_tax_exempt(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        customer.tax_exempt = not customer.tax_exempt
        customer.save(update_fields=["tax_exempt"])
    return redirect(customer.get_absolute_url())


@staff_required
def customer_create_login(request, pk):
    """Staff action: create (or reset) a login for this customer so they can
    use the customer dashboard themselves, instead of only the per-work-order
    link."""
    customer = get_object_or_404(Customer, pk=pk)
    User = get_user_model()

    if request.method == "POST":
        password = get_random_string(12)
        if customer.user:
            customer.user.set_password(password)
            customer.user.save(update_fields=["password"])
            messages.success(request, f"Password reset for {customer.user.username}: {password}")
        else:
            base_username = slugify(customer.name) or f"customer{customer.pk}"
            username = base_username
            n = 1
            while User.objects.filter(username=username).exists():
                n += 1
                username = f"{base_username}{n}"
            user = User.objects.create_user(
                username=username, email=customer.email, password=password, is_staff=False
            )
            customer.user = user
            customer.save(update_fields=["user"])
            messages.success(request, f"Login created — username: {username}, password: {password}")
        messages.warning(request, "Write this password down now; it will not be shown again.")

    return redirect(customer.get_absolute_url())


@staff_required
def technician_list(request):
    technicians = Technician.objects.all()
    return render(request, "shop/technician_list.html", {"technicians": technicians})


@staff_required
def technician_create(request):
    User = get_user_model()
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Name is required.")
            return render(request, "shop/technician_form.html")
        password = get_random_string(12)
        base_username = slugify(name) or "tech"
        username = base_username
        n = 1
        while User.objects.filter(username=username).exists():
            n += 1
            username = f"{base_username}{n}"
        user = User.objects.create_user(username=username, password=password, is_staff=False)
        technician = Technician.objects.create(user=user, name=name, phone=request.POST.get("phone", "").strip())
        log_activity(request.user, "Created technician account", technician)
        messages.success(request, f"Technician login created — username: {username}, password: {password}")
        messages.warning(request, "Write this password down now; it will not be shown again.")
        return redirect("shop:technician_list")
    return render(request, "shop/technician_form.html")


@login_required
def technician_dashboard(request):
    technician = getattr(request.user, "technician_profile", None)
    if technician is None:
        messages.error(request, "This account isn't linked to a technician record.")
        return redirect("dashboard")
    work_orders = technician.work_orders.exclude(status__in=["closed", "invoiced"]).select_related(
        "customer", "vehicle"
    )
    return render(request, "shop/technician_dashboard.html", {"technician": technician, "work_orders": work_orders})


@staff_required
def workorder_list(request):
    work_orders = WorkOrder.objects.select_related("customer", "vehicle").exclude(status="closed")[:300]
    columns = []
    for value, label in WorkOrder.STATUS_CHOICES:
        if value == "closed":
            continue
        columns.append({"value": value, "label": label, "orders": [w for w in work_orders if w.status == value]})
    return render(request, "shop/workorder_list.html", {"columns": columns})


@login_required
def workorder_detail(request, pk):
    work_order = get_object_or_404(
        WorkOrder.objects.select_related("customer", "vehicle", "assigned_technician").prefetch_related(
            "labor_lines", "part_lines", "repair_guides", "inspections", "time_entries"
        ),
        pk=pk,
    )
    if not _can_touch_work_order(request, work_order):
        raise PermissionDenied
    technicians = Technician.objects.filter(active=True) if request.user.is_staff else None
    my_technician = getattr(request.user, "technician_profile", None)
    my_active_time_entry = None
    if my_technician is not None:
        my_active_time_entry = work_order.time_entries.filter(
            technician=my_technician, clock_out__isnull=True
        ).first()
    return render(
        request,
        "shop/workorder_detail.html",
        {
            "work_order": work_order,
            "technicians": technicians,
            "my_active_time_entry": my_active_time_entry,
        },
    )


@staff_required
def workorder_create(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk)
    if request.method == "POST":
        vehicle_id = request.POST.get("vehicle")
        vehicle = get_object_or_404(Vehicle, pk=vehicle_id, owner=customer)
        work_order = WorkOrder.objects.create(
            customer=customer,
            vehicle=vehicle,
            complaint=request.POST.get("complaint", "").strip(),
            odometer=request.POST.get("odometer") or None,
        )
        return redirect(work_order.get_absolute_url())
    return render(request, "shop/workorder_form.html", {"customer": customer})


@login_required
def workorder_add_labor(request, pk):
    work_order = get_object_or_404(WorkOrder, pk=pk)
    if not _can_touch_work_order(request, work_order):
        raise PermissionDenied
    if request.method == "POST":
        LaborLine.objects.create(
            work_order=work_order,
            description=request.POST.get("description", "").strip(),
            hours=request.POST.get("hours") or 0,
            rate=request.POST.get("rate") or 0,
        )
    return redirect(work_order.get_absolute_url())


@login_required
def workorder_add_part(request, pk):
    work_order = get_object_or_404(WorkOrder, pk=pk)
    if not _can_touch_work_order(request, work_order):
        raise PermissionDenied
    if request.method == "POST":
        inventory_id = request.POST.get("inventory_part")
        inventory_part = InventoryPart.objects.filter(pk=inventory_id).first() if inventory_id else None
        quantity = request.POST.get("quantity") or 1

        part_number = request.POST.get("part_number", "").strip()
        description = request.POST.get("description", "").strip()
        unit_price = request.POST.get("unit_price") or 0

        if inventory_part:
            part_number = part_number or inventory_part.part_number
            description = description or inventory_part.description
            unit_price = unit_price or inventory_part.default_price
            InventoryPart.objects.filter(pk=inventory_part.pk).update(
                quantity_on_hand=F("quantity_on_hand") - int(float(quantity))
            )

        PartLine.objects.create(
            work_order=work_order,
            inventory_part=inventory_part,
            part_number=part_number,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
        )
    return redirect(work_order.get_absolute_url())


@login_required
def workorder_update_status(request, pk):
    work_order = get_object_or_404(WorkOrder, pk=pk)
    if not _can_touch_work_order(request, work_order):
        raise PermissionDenied
    if request.method == "POST":
        status = request.POST.get("status", "")
        if status in dict(WorkOrder.STATUS_CHOICES):
            update_fields = ["status", "updated_at"]
            work_order.status = status
            if status in ("completed", "invoiced", "closed") and work_order.completed_at is None:
                work_order.completed_at = timezone.now()
                update_fields.append("completed_at")
            work_order.save(update_fields=update_fields)
            log_activity(request.user, f"Set WO#{work_order.pk} status to {status}", work_order)
    return redirect(work_order.get_absolute_url())


@staff_required
def workorder_assign_technician(request, pk):
    work_order = get_object_or_404(WorkOrder, pk=pk)
    if request.method == "POST":
        tech_id = request.POST.get("technician")
        work_order.assigned_technician = Technician.objects.filter(pk=tech_id).first() if tech_id else None
        work_order.save(update_fields=["assigned_technician"])
    return redirect(work_order.get_absolute_url())


def customer_portal(request, token):
    """Read-only, no-login status page a customer can bookmark for one work
    order. Reachable only by knowing the unguessable token in the URL --
    not linked from anywhere public."""
    work_order = get_object_or_404(
        WorkOrder.objects.select_related("customer", "vehicle").prefetch_related("labor_lines", "part_lines"),
        access_token=token,
    )
    return render(request, "shop/portal.html", {"work_order": work_order})


@login_required
def customer_dashboard(request):
    """Logged-in customer's own view of their vehicles and work orders."""
    customer = getattr(request.user, "customer_profile", None)
    if customer is None:
        messages.error(request, "This account isn't linked to a customer record.")
        return redirect("dashboard")
    vehicles = customer.vehicles.all()
    work_orders = customer.work_orders.select_related("vehicle")[:50]
    pending_estimates = customer.estimates.filter(status="sent").select_related("vehicle")
    upcoming_appointments = customer.appointments.filter(
        scheduled_at__gte=timezone.now(), status__in=["scheduled", "confirmed"]
    ).select_related("vehicle")
    reminders = []
    for vehicle in vehicles:
        reminders += [r for r in vehicle.maintenance_reminders.filter(completed=False) if r.is_due_soon]
    return render(
        request,
        "shop/customer_dashboard.html",
        {
            "customer": customer,
            "vehicles": vehicles,
            "work_orders": work_orders,
            "pending_estimates": pending_estimates,
            "upcoming_appointments": upcoming_appointments,
            "reminders": reminders,
        },
    )


@staff_required
def estimate_list(request):
    estimates = Estimate.objects.select_related("customer", "vehicle").exclude(status="converted")[:300]
    return render(request, "shop/estimate_list.html", {"estimates": estimates})


@staff_required
def estimate_create(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk)
    if request.method == "POST":
        vehicle_id = request.POST.get("vehicle")
        vehicle = get_object_or_404(Vehicle, pk=vehicle_id, owner=customer)
        estimate = Estimate.objects.create(
            customer=customer, vehicle=vehicle, notes=request.POST.get("notes", "").strip()
        )
        return redirect(estimate.get_absolute_url())
    return render(request, "shop/estimate_form.html", {"customer": customer})


@staff_required
def estimate_detail(request, pk):
    estimate = get_object_or_404(
        Estimate.objects.select_related("customer", "vehicle").prefetch_related("labor_lines", "part_lines"),
        pk=pk,
    )
    return render(request, "shop/estimate_detail.html", {"estimate": estimate})


@staff_required
def estimate_add_labor(request, pk):
    estimate = get_object_or_404(Estimate, pk=pk)
    if request.method == "POST":
        EstimateLaborLine.objects.create(
            estimate=estimate,
            description=request.POST.get("description", "").strip(),
            hours=request.POST.get("hours") or 0,
            rate=request.POST.get("rate") or 0,
        )
    return redirect(estimate.get_absolute_url())


@staff_required
def estimate_add_part(request, pk):
    estimate = get_object_or_404(Estimate, pk=pk)
    if request.method == "POST":
        EstimatePartLine.objects.create(
            estimate=estimate,
            part_number=request.POST.get("part_number", "").strip(),
            description=request.POST.get("description", "").strip(),
            quantity=request.POST.get("quantity") or 1,
            unit_price=request.POST.get("unit_price") or 0,
        )
    return redirect(estimate.get_absolute_url())


@staff_required
def estimate_send(request, pk):
    estimate = get_object_or_404(Estimate, pk=pk)
    if request.method == "POST" and estimate.status == "draft":
        estimate.status = "sent"
        estimate.save(update_fields=["status", "updated_at"])
        notify_estimate_sent(estimate)
        messages.success(request, "Marked as sent. Share the customer approval link with them.")
    return redirect(estimate.get_absolute_url())


@staff_required
def estimate_convert(request, pk):
    estimate = get_object_or_404(Estimate, pk=pk)
    if request.method == "POST" and estimate.status in ("approved", "sent", "draft") and not estimate.work_order:
        work_order = WorkOrder.objects.create(
            customer=estimate.customer,
            vehicle=estimate.vehicle,
            complaint=estimate.notes or "See estimate.",
        )
        for line in estimate.labor_lines.all():
            LaborLine.objects.create(
                work_order=work_order, description=line.description, hours=line.hours, rate=line.rate
            )
        for line in estimate.part_lines.all():
            PartLine.objects.create(
                work_order=work_order,
                part_number=line.part_number,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
            )
        estimate.work_order = work_order
        estimate.status = "converted"
        estimate.save(update_fields=["work_order", "status", "updated_at"])
        log_activity(request.user, f"Converted Estimate#{estimate.pk} to WO#{work_order.pk}", estimate)
        return redirect(work_order.get_absolute_url())
    return redirect(estimate.get_absolute_url())


def estimate_portal(request, token):
    """Public, no-login page where a customer can approve or decline an
    estimate. Reachable only by the unguessable token in the URL."""
    estimate = get_object_or_404(
        Estimate.objects.select_related("customer", "vehicle").prefetch_related("labor_lines", "part_lines"),
        access_token=token,
    )
    if request.method == "POST" and estimate.status in ("sent", "draft"):
        decision = request.POST.get("decision")
        if decision == "approve":
            estimate.status = "approved"
            estimate.responded_at = timezone.now()
            signature = request.POST.get("signature_data", "")
            if signature.startswith("data:image/"):
                estimate.signature_data = signature
            estimate.save(update_fields=["status", "responded_at", "signature_data", "updated_at"])
        elif decision == "decline":
            estimate.status = "declined"
            estimate.responded_at = timezone.now()
            estimate.save(update_fields=["status", "responded_at", "updated_at"])
        return redirect(estimate.get_portal_url())
    return render(request, "shop/estimate_portal.html", {"estimate": estimate})


@staff_required
def appointment_calendar(request):
    try:
        week_offset = int(request.GET.get("week", 0))
    except ValueError:
        week_offset = 0
    today = timezone.localdate()
    start_of_week = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=week_offset)
    days = [start_of_week + datetime.timedelta(days=i) for i in range(7)]
    end = days[-1] + datetime.timedelta(days=1)

    appointments = Appointment.objects.filter(
        scheduled_at__date__gte=days[0], scheduled_at__date__lt=end
    ).select_related("customer", "vehicle").exclude(status="cancelled")

    day_buckets = []
    for day in days:
        day_buckets.append(
            {"date": day, "appointments": [a for a in appointments if a.scheduled_at.date() == day]}
        )

    return render(
        request,
        "shop/appointment_calendar.html",
        {"day_buckets": day_buckets, "week_offset": week_offset, "week_start": days[0], "week_end": days[-1]},
    )


@staff_required
def appointment_create(request):
    customer_id = request.GET.get("customer") or request.POST.get("customer")
    customers = Customer.objects.all()
    selected_customer = Customer.objects.filter(pk=customer_id).first() if customer_id else None

    if request.method == "POST":
        customer = get_object_or_404(Customer, pk=request.POST.get("customer"))
        vehicle_id = request.POST.get("vehicle")
        vehicle = Vehicle.objects.filter(pk=vehicle_id, owner=customer).first() if vehicle_id else None
        date_str = request.POST.get("date", "")
        time_str = request.POST.get("time", "")
        try:
            scheduled_at = timezone.make_aware(datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M"))
        except ValueError:
            messages.error(request, "Invalid date/time.")
            return render(
                request,
                "shop/appointment_form.html",
                {"customers": customers, "customer_id": customer_id, "selected_customer": customer},
            )
        appointment = Appointment.objects.create(
            customer=customer,
            vehicle=vehicle,
            scheduled_at=scheduled_at,
            duration_minutes=request.POST.get("duration_minutes") or 60,
            reason=request.POST.get("reason", "").strip(),
        )
        notify_appointment_created(appointment)
        return redirect("shop:appointment_calendar")
    return render(
        request,
        "shop/appointment_form.html",
        {"customers": customers, "customer_id": customer_id, "selected_customer": selected_customer},
    )


def appointments_ics_feed(request, token):
    """Subscribe URL (webcal/https) for the appointment calendar, gated by
    an unguessable token from ShopSettings rather than a login -- calendar
    apps can't do a Django login flow when polling a feed."""
    settings_obj = ShopSettings.get_solo()
    if str(settings_obj.calendar_feed_token) != str(token):
        raise Http404
    appointments = Appointment.objects.filter(
        scheduled_at__gte=timezone.now() - datetime.timedelta(days=7),
        scheduled_at__lte=timezone.now() + datetime.timedelta(days=180),
    ).exclude(status="cancelled").select_related("customer", "vehicle")
    response = HttpResponse(build_appointments_ics(appointments), content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="repairhub-appointments.ics"'
    return response


@staff_required
def appointment_detail(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related("customer", "vehicle"), pk=pk)
    return render(request, "shop/appointment_detail.html", {"appointment": appointment})


@staff_required
def appointment_update_status(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == "POST":
        status = request.POST.get("status", "")
        if status in dict(Appointment.STATUS_CHOICES):
            appointment.status = status
            appointment.save(update_fields=["status"])
    return redirect(appointment.get_absolute_url())


@staff_required
def appointment_start_work_order(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == "POST" and not appointment.work_order and appointment.vehicle:
        work_order = WorkOrder.objects.create(
            customer=appointment.customer, vehicle=appointment.vehicle, complaint=appointment.reason
        )
        appointment.work_order = work_order
        appointment.status = "completed"
        appointment.save(update_fields=["work_order", "status"])
        return redirect(work_order.get_absolute_url())
    return redirect(appointment.get_absolute_url())


@staff_or_technician_required
def inventory_list(request):
    parts = InventoryPart.objects.all()
    return render(request, "shop/inventory_list.html", {"parts": parts})


@staff_required
def inventory_create(request):
    if request.method == "POST":
        InventoryPart.objects.create(
            part_number=request.POST.get("part_number", "").strip(),
            description=request.POST.get("description", "").strip(),
            quantity_on_hand=request.POST.get("quantity_on_hand") or 0,
            reorder_point=request.POST.get("reorder_point") or 0,
            unit_cost=request.POST.get("unit_cost") or 0,
            default_price=request.POST.get("default_price") or 0,
            location=request.POST.get("location", "").strip(),
        )
        return redirect("shop:inventory_list")
    return render(request, "shop/inventory_form.html")


@staff_or_technician_required
def inventory_parts_json(request):
    query = request.GET.get("q", "").strip()
    parts = InventoryPart.objects.all()
    if query:
        parts = parts.filter(part_number__icontains=query) | parts.filter(description__icontains=query)
    return JsonResponse(
        {
            "parts": [
                {
                    "id": p.pk,
                    "part_number": p.part_number,
                    "description": p.description,
                    "unit_price": str(p.default_price),
                    "quantity_on_hand": p.quantity_on_hand,
                }
                for p in parts[:20]
            ]
        }
    )


@staff_or_technician_required
def inspection_create(request, work_order_pk):
    work_order = get_object_or_404(WorkOrder, pk=work_order_pk)
    if not _can_touch_work_order(request, work_order):
        raise PermissionDenied
    technician = getattr(request.user, "technician_profile", None)
    inspection = Inspection.objects.create(work_order=work_order, technician=technician)
    inspection.create_default_items()
    return redirect(inspection.get_absolute_url())


@login_required
def inspection_detail(request, pk):
    inspection = get_object_or_404(
        Inspection.objects.select_related("work_order", "work_order__vehicle").prefetch_related("items"), pk=pk
    )
    if not _can_touch_work_order(request, inspection.work_order):
        raise PermissionDenied
    return render(request, "shop/inspection_detail.html", {"inspection": inspection})


@login_required
def inspection_item_update(request, pk):
    item = get_object_or_404(InspectionItem.objects.select_related("inspection__work_order"), pk=pk)
    if not _can_touch_work_order(request, item.inspection.work_order):
        raise PermissionDenied
    if request.method == "POST":
        item.status = request.POST.get("status", item.status)
        item.notes = request.POST.get("notes", "").strip()
        if request.FILES.get("photo"):
            item.photo = request.FILES["photo"]
        item.save()
    return redirect(item.inspection.get_absolute_url())


def inspection_portal(request, token):
    inspection = get_object_or_404(
        Inspection.objects.select_related("work_order", "work_order__vehicle").prefetch_related("items"),
        access_token=token,
    )
    return render(request, "shop/inspection_portal.html", {"inspection": inspection})


@staff_required
def inspection_create_estimate(request, pk):
    inspection = get_object_or_404(Inspection.objects.select_related("work_order"), pk=pk)
    if request.method == "POST":
        flagged = inspection.items.exclude(status="green")
        notes = "Follow-up from inspection:\n" + "\n".join(
            f"- [{i.get_status_display()}] {i.description}" + (f" — {i.notes}" if i.notes else "")
            for i in flagged
        )
        estimate = Estimate.objects.create(
            customer=inspection.work_order.customer, vehicle=inspection.work_order.vehicle, notes=notes
        )
        return redirect(estimate.get_absolute_url())
    return redirect(inspection.get_absolute_url())


@staff_required
def workorder_pdf(request, pk):
    from xhtml2pdf import pisa  # heavy import, only needed here

    work_order = get_object_or_404(
        WorkOrder.objects.select_related("customer", "vehicle").prefetch_related("labor_lines", "part_lines"), pk=pk
    )
    html = render(request, "shop/pdf/workorder_pdf.html", {"work_order": work_order}).content.decode("utf-8")
    buf = io.BytesIO()
    pisa.CreatePDF(html, dest=buf)
    response = HttpResponse(buf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice-wo{work_order.pk}.pdf"'
    return response


@staff_required
def estimate_pdf(request, pk):
    from xhtml2pdf import pisa  # heavy import, only needed here

    estimate = get_object_or_404(
        Estimate.objects.select_related("customer", "vehicle").prefetch_related("labor_lines", "part_lines"), pk=pk
    )
    html = render(request, "shop/pdf/estimate_pdf.html", {"estimate": estimate}).content.decode("utf-8")
    buf = io.BytesIO()
    pisa.CreatePDF(html, dest=buf)
    response = HttpResponse(buf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="estimate-{estimate.pk}.pdf"'
    return response


@staff_required
def reports_dashboard(request):
    try:
        days = int(request.GET.get("days", 30))
    except ValueError:
        days = 30
    since = timezone.now() - datetime.timedelta(days=days)

    completed_orders = WorkOrder.objects.filter(
        status__in=["completed", "invoiced", "closed"], updated_at__gte=since
    ).prefetch_related("labor_lines", "part_lines", "repair_guides")

    total_revenue = sum((wo.grand_total for wo in completed_orders), start=0)
    order_count = completed_orders.count()
    avg_ticket = (total_revenue / order_count) if order_count else 0

    status_counts = []
    for value, label in WorkOrder.STATUS_CHOICES:
        status_counts.append({"label": label, "count": WorkOrder.objects.filter(status=value).count()})

    guide_counts = {}
    part_counts = {}
    timed_orders = []
    for wo in completed_orders:
        for guide in wo.repair_guides.all():
            guide_counts[guide] = guide_counts.get(guide, 0) + 1
        for line in wo.part_lines.all():
            key = line.description
            part_counts[key] = part_counts.get(key, 0) + line.quantity
        if wo.completed_at:
            timed_orders.append((wo.completed_at - wo.created_at).total_seconds())
    top_guides = sorted(guide_counts.items(), key=lambda x: -x[1])[:10]
    top_parts = sorted(part_counts.items(), key=lambda x: -x[1])[:10]
    avg_repair_hours = (sum(timed_orders) / len(timed_orders) / 3600) if timed_orders else None

    low_stock = InventoryPart.objects.all()
    low_stock = [p for p in low_stock if p.is_low_stock]

    outstanding_balance = sum(
        (inv.balance_due for inv in Invoice.objects.filter(paid=False).select_related("work_order")),
        start=Decimal("0.00"),
    )

    revenue_by_month = []
    month_start = timezone.localdate().replace(day=1)
    for i in range(5, -1, -1):
        year = month_start.year
        month = month_start.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_orders = WorkOrder.objects.filter(
            status__in=["completed", "invoiced", "closed"], completed_at__year=year, completed_at__month=month
        ).prefetch_related("labor_lines", "part_lines")
        revenue_by_month.append(
            {
                "label": datetime.date(year, month, 1).strftime("%b %Y"),
                "total": sum((wo.grand_total for wo in month_orders), start=Decimal("0.00")),
            }
        )
    max_month_revenue = max((m["total"] for m in revenue_by_month), default=Decimal("0.00")) or Decimal("1.00")
    for m in revenue_by_month:
        m["bar_percent"] = int((m["total"] / max_month_revenue) * 100)

    return render(
        request,
        "shop/reports.html",
        {
            "days": days,
            "total_revenue": total_revenue,
            "order_count": order_count,
            "avg_ticket": avg_ticket,
            "status_counts": status_counts,
            "top_guides": top_guides,
            "top_parts": top_parts,
            "avg_repair_hours": avg_repair_hours,
            "low_stock": low_stock,
            "outstanding_balance": outstanding_balance,
            "revenue_by_month": revenue_by_month,
        },
    )


@staff_required
def activity_log(request):
    entries = ActivityLogEntry.objects.select_related("user")[:200]
    return render(request, "shop/activity_log.html", {"entries": entries})


@staff_required
def shop_settings_view(request):
    settings_obj = ShopSettings.get_solo()
    if request.method == "POST":
        settings_obj.business_name = request.POST.get("business_name", "").strip()
        settings_obj.tax_rate_percent = request.POST.get("tax_rate_percent") or 0
        settings_obj.save()
        messages.success(request, "Settings saved.")
        return redirect("shop:settings")
    feed_path = reverse("shop:appointments_ics_feed", args=[settings_obj.calendar_feed_token])
    calendar_feed_url = request.build_absolute_uri(feed_path)
    return render(
        request, "shop/settings.html", {"settings": settings_obj, "calendar_feed_url": calendar_feed_url}
    )


@staff_required
def regenerate_calendar_feed_token(request):
    settings_obj = ShopSettings.get_solo()
    if request.method == "POST":
        settings_obj.regenerate_calendar_feed_token()
        messages.success(request, "Calendar feed link regenerated -- update it in any calendar app that had the old one.")
    return redirect("shop:settings")


@staff_required
def workorder_set_warranty(request, pk):
    work_order = get_object_or_404(WorkOrder, pk=pk)
    if request.method == "POST":
        work_order.warranty_months = request.POST.get("warranty_months") or None
        work_order.warranty_miles = request.POST.get("warranty_miles") or None
        work_order.save(update_fields=["warranty_months", "warranty_miles"])
    return redirect(work_order.get_absolute_url())


@staff_required
def workorder_create_invoice(request, pk):
    work_order = get_object_or_404(WorkOrder, pk=pk)
    if request.method == "POST" and not hasattr(work_order, "invoice"):
        invoice_number = f"INV-{work_order.pk:05d}"
        invoice = Invoice.objects.create(work_order=work_order, invoice_number=invoice_number)
        work_order.status = "invoiced"
        work_order.save(update_fields=["status", "updated_at"])
        log_activity(request.user, f"Created {invoice_number} for WO#{work_order.pk}", invoice)
        notify_invoice_created(invoice)
        return redirect("shop:invoice_detail", pk=invoice.pk)
    if hasattr(work_order, "invoice"):
        return redirect("shop:invoice_detail", pk=work_order.invoice.pk)
    return redirect(work_order.get_absolute_url())


@staff_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("work_order", "work_order__customer", "work_order__vehicle").prefetch_related(
            "payments"
        ),
        pk=pk,
    )
    return render(request, "shop/invoice_detail.html", {"invoice": invoice})


@staff_required
def invoice_add_payment(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == "POST":
        PaymentRecord.objects.create(
            invoice=invoice,
            amount=request.POST.get("amount") or 0,
            method=request.POST.get("method", "card"),
            notes=request.POST.get("notes", "").strip(),
        )
        if invoice.is_fully_paid and not invoice.paid:
            invoice.paid = True
            invoice.paid_date = timezone.localdate()
            invoice.save(update_fields=["paid", "paid_date"])
    return redirect("shop:invoice_detail", pk=invoice.pk)


@staff_required
def export_invoices_csv(request):
    start = request.GET.get("start", "")
    end = request.GET.get("end", "")
    invoices = Invoice.objects.select_related("work_order", "work_order__customer").prefetch_related("payments")
    if start:
        invoices = invoices.filter(issued_date__gte=start)
    if end:
        invoices = invoices.filter(issued_date__lte=end)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="repairhub-invoices.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ["Date", "Invoice #", "Customer", "Work Order", "Labor", "Parts", "Tax", "Total", "Amount Paid", "Balance Due"]
    )
    for inv in invoices:
        wo = inv.work_order
        writer.writerow(
            [
                inv.issued_date,
                inv.invoice_number,
                wo.customer.name,
                f"WO#{wo.pk}",
                wo.labor_total,
                wo.parts_total,
                wo.tax_total,
                wo.grand_total,
                inv.amount_paid,
                inv.balance_due,
            ]
        )
    return response


def _tech_or_403(request):
    tech = getattr(request.user, "technician_profile", None)
    if tech is None:
        raise PermissionDenied("Time clock is only available to technician accounts.")
    return tech


@login_required
def workorder_clock_in(request, pk):
    work_order = get_object_or_404(WorkOrder, pk=pk)
    technician = _tech_or_403(request)
    if not _can_touch_work_order(request, work_order):
        raise PermissionDenied
    if request.method == "POST":
        if not TimeEntry.objects.filter(work_order=work_order, technician=technician, clock_out__isnull=True).exists():
            TimeEntry.objects.create(work_order=work_order, technician=technician)
    return redirect(work_order.get_absolute_url())


@login_required
def workorder_clock_out(request, pk):
    work_order = get_object_or_404(WorkOrder, pk=pk)
    technician = _tech_or_403(request)
    if not _can_touch_work_order(request, work_order):
        raise PermissionDenied
    if request.method == "POST":
        entry = TimeEntry.objects.filter(
            work_order=work_order, technician=technician, clock_out__isnull=True
        ).first()
        if entry:
            entry.clock_out = timezone.now()
            entry.save(update_fields=["clock_out"])
    return redirect(work_order.get_absolute_url())
