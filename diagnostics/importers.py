"""Shared bulk-import logic for DTC codes, used by both the
`import_dtc_codes` management command and the web-based import UI."""
import csv
import io

from vehicles.models import Make

from .models import DTCCode


class DTCImportError(Exception):
    pass


def import_dtc_codes_from_csv(file_obj):
    if hasattr(file_obj, "read"):
        raw = file_obj.read()
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
        reader = csv.DictReader(io.StringIO(text))
    else:
        reader = csv.DictReader(file_obj)

    required = {"code", "description"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise DTCImportError(f"CSV must have at least these columns: {sorted(required)}")

    created = updated = 0
    for row in reader:
        code = (row.get("code") or "").strip().upper()
        description = (row.get("description") or "").strip()
        if not code or not description:
            continue

        make_name = (row.get("make") or "").strip()
        make = None
        if make_name:
            make, _ = Make.objects.get_or_create(name=make_name)

        system = (row.get("system") or code[0]).strip().upper()
        origin = (row.get("origin") or ("manufacturer" if make else "generic")).strip().lower()

        _, was_created = DTCCode.objects.update_or_create(
            code=code,
            defaults={
                "description": description,
                "system": system,
                "origin": origin,
                "make": make,
                "likely_causes": (row.get("likely_causes") or "").strip(),
                "diagnostic_steps": (row.get("diagnostic_steps") or "").strip(),
            },
        )
        created += int(was_created)
        updated += int(not was_created)

    return {"created": created, "updated": updated}
