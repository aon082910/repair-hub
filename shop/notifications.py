"""Best-effort email notifications for appointments, estimates, and invoices.

Sends only when the customer has an email on file. Never raises -- a
misconfigured or unreachable mail server shouldn't break the request that
triggered the notification (creating an appointment, sending an estimate,
etc). With no EMAIL_HOST configured, Django's console backend just logs the
message, so this is safe to call unconditionally.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _send(subject: str, body: str, to_email: str) -> None:
    if not to_email:
        return
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)
    except Exception:
        logger.exception("Failed to send notification email to %s", to_email)


def notify_appointment_created(appointment) -> None:
    when = appointment.scheduled_at.strftime("%A, %B %d, %Y at %I:%M %p")
    _send(
        subject=f"Appointment scheduled - {when}",
        body=(
            f"Hi {appointment.customer.name},\n\n"
            f"You're scheduled for {when} ({appointment.reason}).\n\n"
            "Reply to this email or call us if you need to reschedule."
        ),
        to_email=appointment.customer.email,
    )


def notify_estimate_sent(estimate) -> None:
    portal_url = estimate.get_portal_url()
    _send(
        subject=f"Estimate ready for review - {estimate.vehicle}",
        body=(
            f"Hi {estimate.customer.name},\n\n"
            f"An estimate for your {estimate.vehicle} (${estimate.grand_total:.2f}) is ready for your review.\n"
            f"View and approve it here: {portal_url}\n\n"
            "This link doesn't require a login."
        ),
        to_email=estimate.customer.email,
    )


def notify_invoice_created(invoice) -> None:
    work_order = invoice.work_order
    portal_url = work_order.get_portal_url()
    _send(
        subject=f"Invoice {invoice.invoice_number} - {work_order.vehicle}",
        body=(
            f"Hi {work_order.customer.name},\n\n"
            f"Invoice {invoice.invoice_number} for your {work_order.vehicle} is ready: "
            f"${work_order.grand_total:.2f} due.\n"
            f"View your service status here: {portal_url}"
        ),
        to_email=work_order.customer.email,
    )
