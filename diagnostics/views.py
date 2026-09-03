from django.contrib import messages
from django.shortcuts import get_object_or_404, render

from core.decorators import staff_or_technician_required, staff_required
from repairguides.models import RepairGuide

from .importers import DTCImportError, import_dtc_codes_from_csv
from .models import DTCCode


@staff_or_technician_required
def dtc_list(request):
    query = request.GET.get("q", "").strip().upper()
    codes = DTCCode.objects.select_related("make")
    if query:
        codes = codes.filter(code__icontains=query) | codes.filter(description__icontains=query)
    return render(request, "diagnostics/dtc_list.html", {"codes": codes[:300], "query": query})


@staff_or_technician_required
def dtc_detail(request, code):
    dtc = get_object_or_404(DTCCode.objects.select_related("make"), code__iexact=code)
    related_guides = RepairGuide.objects.filter(dtc_codes=dtc).select_related("vehicle", "system")
    return render(request, "diagnostics/dtc_detail.html", {"dtc": dtc, "related_guides": related_guides})


@staff_required
def import_codes_view(request):
    stats = None
    if request.method == "POST" and request.FILES.get("csv_file"):
        try:
            stats = import_dtc_codes_from_csv(request.FILES["csv_file"])
            messages.success(request, f"Import complete: {stats['created']} created, {stats['updated']} updated.")
        except DTCImportError as exc:
            messages.error(request, f"Import failed: {exc}")
    return render(request, "diagnostics/import_codes.html", {"stats": stats})
