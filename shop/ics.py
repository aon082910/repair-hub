"""Minimal iCalendar (RFC 5545) feed generation for the appointment
calendar -- no external dependency, just enough VEVENT fields for Google
Calendar / Apple Calendar / Outlook to subscribe to."""
from django.utils import timezone


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _fold(line: str) -> str:
    # RFC 5545 line folding: continuation lines start with a single space.
    if len(line) <= 75:
        return line
    parts = [line[:75]]
    rest = line[75:]
    while rest:
        parts.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(parts)


def build_appointments_ics(appointments) -> str:
    now_stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Repair-Hub//Appointments//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Repair-Hub Appointments",
    ]
    for appt in appointments:
        start = timezone.localtime(appt.scheduled_at)
        end = start + timezone.timedelta(minutes=appt.duration_minutes)
        summary = _escape(f"{appt.reason} - {appt.customer.name}")
        description_parts = [f"Status: {appt.get_status_display()}"]
        if appt.vehicle:
            description_parts.append(f"Vehicle: {appt.vehicle}")
        if appt.notes:
            description_parts.append(appt.notes)
        description = _escape("\n".join(description_parts))
        lines += [
            "BEGIN:VEVENT",
            f"UID:repairhub-appointment-{appt.pk}@repair-hub",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
