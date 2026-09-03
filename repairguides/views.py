import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from core.decorators import staff_or_technician_required, staff_required

from .external import search_commons_images, search_ifixit
from .importers import GuideImportError, import_guides_from_records
from .models import RepairGuide, System, WiringDiagram


@staff_or_technician_required
def guide_list(request):
    query = request.GET.get("q", "").strip()
    system_id = request.GET.get("system", "")
    guides = RepairGuide.objects.select_related("system", "vehicle", "make", "model")
    if query:
        guides = guides.filter(title__icontains=query)
    if system_id:
        guides = guides.filter(system_id=system_id)
    return render(
        request,
        "repairguides/guide_list.html",
        {"guides": guides[:200], "systems": System.objects.all(), "query": query, "system_id": system_id},
    )


@staff_or_technician_required
def guide_detail(request, pk):
    guide = get_object_or_404(
        RepairGuide.objects.select_related("system", "vehicle", "make", "model").prefetch_related(
            "steps__images", "images", "dtc_codes"
        ),
        pk=pk,
    )
    extra_images = guide.images.filter(step__isnull=True)
    return render(request, "repairguides/guide_detail.html", {"guide": guide, "extra_images": extra_images})


@staff_or_technician_required
def wiring_diagram_list(request):
    query = request.GET.get("q", "").strip()
    diagrams = WiringDiagram.objects.select_related("system", "vehicle", "make", "model")
    if query:
        diagrams = diagrams.filter(title__icontains=query)
    return render(request, "repairguides/wiring_diagram_list.html", {"diagrams": diagrams[:200], "query": query})


@staff_or_technician_required
def external_search(request):
    """Search free/open external sources (iFixit guides + Wikimedia Commons
    reference photos) and link out to them -- no proprietary or
    ToS-restricted content."""
    query = request.GET.get("q", "").strip()
    guide_results = search_ifixit(query) if query else []
    image_results = search_commons_images(query) if query else []
    return render(
        request,
        "repairguides/external_search.html",
        {"query": query, "results": guide_results, "images": image_results},
    )


@staff_or_technician_required
def external_search_json(request):
    query = request.GET.get("q", "").strip()
    return JsonResponse({"results": search_ifixit(query) if query else []})


@staff_or_technician_required
def commons_search_json(request):
    query = request.GET.get("q", "").strip()
    return JsonResponse({"images": search_commons_images(query) if query else []})


@staff_required
def import_guides_view(request):
    stats = None
    if request.method == "POST" and request.FILES.get("json_file"):
        update = bool(request.POST.get("update"))
        try:
            records = json.load(request.FILES["json_file"])
            stats = import_guides_from_records(records, update=update)
            if stats["skipped"]:
                for msg in stats["skipped"]:
                    messages.warning(request, msg)
            messages.success(
                request,
                f"Import complete: {stats['created']} created, {stats['updated']} updated, "
                f"{len(stats['skipped'])} skipped.",
            )
        except (json.JSONDecodeError, GuideImportError) as exc:
            messages.error(request, f"Import failed: {exc}")
    return render(request, "repairguides/import_guides.html", {"stats": stats})
