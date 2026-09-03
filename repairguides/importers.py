"""Shared bulk-import logic for repair guides, used by both the
`import_guides` management command and the web-based import UI."""
from diagnostics.models import DTCCode
from vehicles.models import Make, Vehicle, VehicleModel

from .models import GuideStep, RepairGuide, System


class GuideImportError(Exception):
    pass


def import_guides_from_records(records, update=False):
    if not isinstance(records, list):
        raise GuideImportError("Expected the JSON to contain a list of guide objects.")

    created_count = 0
    updated_count = 0
    skipped = []

    for i, rec in enumerate(records):
        title = (rec.get("title") or "").strip()
        system_name = (rec.get("system") or "").strip()
        if not title or not system_name:
            skipped.append(f"Record {i}: missing title or system")
            continue

        system, _ = System.objects.get_or_create(name=system_name)

        make = model = vehicle = None
        make_name = (rec.get("make") or "").strip()
        model_name = (rec.get("model") or "").strip()
        vin = (rec.get("vin") or "").strip()

        if make_name:
            make, _ = Make.objects.get_or_create(name=make_name)
        if make and model_name:
            model, _ = VehicleModel.objects.get_or_create(make=make, name=model_name)
        if vin:
            vehicle = Vehicle.objects.filter(vin__iexact=vin).first()

        existing = RepairGuide.objects.filter(title=title, system=system).first()
        if existing and not update:
            skipped.append(f"Already exists: {title}")
            continue

        guide = existing or RepairGuide()
        guide.title = title
        guide.system = system
        guide.summary = rec.get("summary", "")
        guide.make = make
        guide.model = model
        guide.vehicle = vehicle
        guide.year_start = rec.get("year_start") or None
        guide.year_end = rec.get("year_end") or None
        guide.save()

        if existing:
            guide.steps.all().delete()
            updated_count += 1
        else:
            created_count += 1

        for step in rec.get("steps", []):
            GuideStep.objects.create(
                guide=guide,
                order=step.get("order", 1),
                instructions=step.get("instructions", ""),
                torque_spec=step.get("torque_spec", ""),
                caution=step.get("caution", ""),
            )

        dtc_codes = rec.get("dtc_codes", [])
        if dtc_codes:
            guide.dtc_codes.set(DTCCode.objects.filter(code__in=dtc_codes))

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped,
        "total": len(records),
    }
