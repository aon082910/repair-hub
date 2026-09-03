import io

import qrcode
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.decorators import staff_or_technician_required
from integrations.models import AllDataAttachment, AllDataLink
from repairguides.models import RepairGuide, WiringDiagram

from .models import MaintenanceReminder, Make, Vehicle, VehicleModel
from .recalls import get_complaints, get_recalls
from .specs import find_vehicle_options, get_vehicle_specs
from .vin import decode_vin


@staff_or_technician_required
def vehicle_list(request):
    query = request.GET.get("q", "").strip()
    vehicles = Vehicle.objects.select_related("make", "model", "owner")
    if query:
        vehicles = vehicles.filter(vin__icontains=query) | vehicles.filter(
            model__name__icontains=query
        ) | vehicles.filter(make__name__icontains=query)
    return render(request, "vehicles/vehicle_list.html", {"vehicles": vehicles[:200], "query": query})


@staff_or_technician_required
def vehicle_detail(request, pk):
    vehicle = get_object_or_404(Vehicle.objects.select_related("make", "model", "owner"), pk=pk)
    guides = RepairGuide.objects.filter(vehicle=vehicle).select_related("system")
    diagrams = WiringDiagram.objects.filter(vehicle=vehicle).select_related("system")
    alldata_links = AllDataLink.objects.filter(vehicle=vehicle)
    alldata_files = AllDataAttachment.objects.filter(vehicle=vehicle)
    reminders = vehicle.maintenance_reminders.all()
    return render(
        request,
        "vehicles/vehicle_detail.html",
        {
            "vehicle": vehicle,
            "guides": guides,
            "diagrams": diagrams,
            "alldata_links": alldata_links,
            "alldata_files": alldata_files,
            "reminders": reminders,
        },
    )


@staff_or_technician_required
def vin_lookup(request):
    """AJAX endpoint: decode a VIN via the public NHTSA API and return best-guess fields."""
    vin = request.GET.get("vin", "")
    return JsonResponse(decode_vin(vin))


@staff_or_technician_required
def recalls_data(request, pk):
    """AJAX endpoint: recalls + complaints for a vehicle via NHTSA's free public API."""
    vehicle = get_object_or_404(Vehicle, pk=pk)
    recalls = get_recalls(vehicle.make.name, vehicle.model.name, vehicle.year)
    complaints = get_complaints(vehicle.make.name, vehicle.model.name, vehicle.year)
    return JsonResponse({"recalls": recalls, "complaints": complaints})


@staff_or_technician_required
def makes_json(request):
    return JsonResponse({"makes": list(Make.objects.order_by("name").values_list("name", flat=True))})


@staff_or_technician_required
def models_json(request):
    make_name = request.GET.get("make", "").strip()
    models = VehicleModel.objects.filter(make__name__iexact=make_name).order_by("name") if make_name else []
    return JsonResponse({"models": [m.name for m in models]})


@staff_or_technician_required
def specs_data(request, pk):
    """AJAX endpoint: vehicle specs via the free public EPA fueleconomy.gov API."""
    vehicle = get_object_or_404(Vehicle, pk=pk)
    options = find_vehicle_options(vehicle.year, vehicle.make.name, vehicle.model.name)
    if not options:
        return JsonResponse({"specs": {}, "options": []})
    specs = get_vehicle_specs(options[0]["id"])
    return JsonResponse({"specs": specs, "options": options})


@staff_or_technician_required
def vehicle_create(request):
    if request.method == "POST":
        year = request.POST.get("year")
        make_name = request.POST.get("make", "").strip()
        model_name = request.POST.get("model", "").strip()
        vin = request.POST.get("vin", "").strip().upper()
        trim = request.POST.get("trim", "").strip()
        engine = request.POST.get("engine", "").strip()

        if year and make_name and model_name:
            make, _ = Make.objects.get_or_create(name=make_name)
            model, _ = VehicleModel.objects.get_or_create(make=make, name=model_name)
            vehicle = Vehicle.objects.create(
                year=year, make=make, model=model, vin=vin, trim=trim, engine=engine
            )
            return redirect(vehicle.get_absolute_url())

    return render(request, "vehicles/vehicle_form.html")


@staff_or_technician_required
def reminder_create(request, vehicle_pk):
    vehicle = get_object_or_404(Vehicle, pk=vehicle_pk)
    if request.method == "POST":
        MaintenanceReminder.objects.create(
            vehicle=vehicle,
            description=request.POST.get("description", "").strip(),
            due_date=request.POST.get("due_date") or None,
            due_mileage=request.POST.get("due_mileage") or None,
            interval_months=request.POST.get("interval_months") or None,
            interval_miles=request.POST.get("interval_miles") or None,
            notes=request.POST.get("notes", "").strip(),
        )
    return redirect(vehicle.get_absolute_url())


@staff_or_technician_required
def reminder_mark_done(request, pk):
    reminder = get_object_or_404(MaintenanceReminder, pk=pk)
    if request.method == "POST":
        reminder.mark_done()
    return redirect(reminder.vehicle.get_absolute_url())


def service_history(request, token):
    """Public, no-login read-only service history for one vehicle -- reached
    via the QR code on its detail page. Shows completed work order summaries
    only, no financial detail or customer info."""
    vehicle = get_object_or_404(Vehicle.objects.select_related("make", "model"), access_token=token)
    work_orders = vehicle.work_orders.filter(status__in=["completed", "invoiced", "closed"]).order_by(
        "-created_at"
    )
    return render(request, "vehicles/service_history.html", {"vehicle": vehicle, "work_orders": work_orders})


@staff_or_technician_required
def vehicle_qr_code(request, pk):
    """Return a PNG QR code pointing at this vehicle's public service-history page."""
    vehicle = get_object_or_404(Vehicle, pk=pk)
    url = request.build_absolute_uri(vehicle.get_service_history_url())
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")
