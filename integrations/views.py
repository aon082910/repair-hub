from django.shortcuts import get_object_or_404, redirect

from core.decorators import staff_required
from vehicles.models import Vehicle

from .models import AllDataAttachment, AllDataLink


@staff_required
def add_link(request, vehicle_pk):
    vehicle = get_object_or_404(Vehicle, pk=vehicle_pk)
    if request.method == "POST":
        AllDataLink.objects.create(
            vehicle=vehicle,
            label=request.POST.get("label", "").strip(),
            url=request.POST.get("url", "").strip(),
            note=request.POST.get("note", "").strip(),
        )
    return redirect(vehicle.get_absolute_url())


@staff_required
def add_attachment(request, vehicle_pk):
    vehicle = get_object_or_404(Vehicle, pk=vehicle_pk)
    if request.method == "POST" and request.FILES.get("file"):
        AllDataAttachment.objects.create(
            vehicle=vehicle,
            file=request.FILES["file"],
            description=request.POST.get("description", "").strip(),
        )
    return redirect(vehicle.get_absolute_url())
