import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from vehicles.models import Make, Vehicle, VehicleModel

from .ics import build_appointments_ics
from .models import (
    Appointment,
    Customer,
    Estimate,
    Inspection,
    Invoice,
    InventoryPart,
    LaborLine,
    PartLine,
    ShopSettings,
    Technician,
    TimeEntry,
    WorkOrder,
)

User = get_user_model()


def make_vehicle():
    make, _ = Make.objects.get_or_create(name="Honda")
    model, _ = VehicleModel.objects.get_or_create(make=make, name="Civic")
    return Vehicle.objects.create(year=2018, make=make, model=model)


def make_staff(username="staff"):
    return User.objects.create_user(username=username, password="pw", is_staff=True)


class WorkOrderTotalsTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Noise")

    def test_labor_and_parts_totals(self):
        LaborLine.objects.create(work_order=self.wo, description="Replace pads", hours=Decimal("1.5"), rate=Decimal("90"))
        PartLine.objects.create(work_order=self.wo, description="Pad set", quantity=1, unit_price=Decimal("45"))
        self.assertEqual(self.wo.labor_total, Decimal("135.00"))
        self.assertEqual(self.wo.parts_total, Decimal("45.00"))
        self.assertEqual(self.wo.grand_total, Decimal("180.00"))

    def test_grand_total_zero_with_no_lines(self):
        self.assertEqual(self.wo.grand_total, Decimal("0.00"))

    def test_tax_applied_when_rate_set(self):
        settings_obj = ShopSettings.get_solo()
        settings_obj.tax_rate_percent = Decimal("10.00")
        settings_obj.save()
        LaborLine.objects.create(work_order=self.wo, description="Labor", hours=1, rate=Decimal("100"))
        self.assertEqual(self.wo.tax_total, Decimal("10.00"))
        self.assertEqual(self.wo.grand_total, Decimal("110.00"))

    def test_tax_exempt_customer_pays_no_tax(self):
        settings_obj = ShopSettings.get_solo()
        settings_obj.tax_rate_percent = Decimal("10.00")
        settings_obj.save()
        self.customer.tax_exempt = True
        self.customer.save()
        LaborLine.objects.create(work_order=self.wo, description="Labor", hours=1, rate=Decimal("100"))
        self.assertEqual(self.wo.tax_total, Decimal("0.00"))
        self.assertEqual(self.wo.grand_total, Decimal("100.00"))

    def test_no_tax_when_rate_is_zero(self):
        LaborLine.objects.create(work_order=self.wo, description="Labor", hours=1, rate=Decimal("100"))
        self.assertEqual(self.wo.tax_total, Decimal("0.00"))

    def test_portal_url_uses_access_token(self):
        self.assertIn(str(self.wo.access_token), self.wo.get_portal_url())


class WarrantyTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()

    def test_under_warranty_when_recently_completed(self):
        wo = WorkOrder.objects.create(
            customer=self.customer, vehicle=self.vehicle, complaint="Brakes",
            warranty_months=12, completed_at=timezone.now(),
        )
        self.assertTrue(wo.is_under_warranty)
        self.assertIsNotNone(wo.warranty_expiration_date)

    def test_not_under_warranty_when_expired(self):
        wo = WorkOrder.objects.create(
            customer=self.customer, vehicle=self.vehicle, complaint="Brakes",
            warranty_months=1, completed_at=timezone.now() - datetime.timedelta(days=200),
        )
        self.assertFalse(wo.is_under_warranty)

    def test_no_warranty_set_is_not_under_warranty(self):
        wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Brakes")
        self.assertFalse(wo.is_under_warranty)
        self.assertIsNone(wo.warranty_expiration_date)

    def test_mileage_warranty_exceeded_voids_warranty(self):
        wo = WorkOrder.objects.create(
            customer=self.customer, vehicle=self.vehicle, complaint="Brakes",
            warranty_months=12, warranty_miles=1000, odometer=10000,
            completed_at=timezone.now(),
        )
        WorkOrder.objects.create(
            customer=self.customer, vehicle=self.vehicle, complaint="later reading", odometer=12000
        )
        self.assertFalse(wo.is_under_warranty)


class WorkOrderAccessControlTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Noise")

        self.tech_user = User.objects.create_user(username="tech", password="pw")
        self.technician = Technician.objects.create(user=self.tech_user, name="Bob")

        self.other_tech_user = User.objects.create_user(username="tech2", password="pw")
        self.other_technician = Technician.objects.create(user=self.other_tech_user, name="Alice")

    def test_staff_can_view_any_work_order(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.get(self.wo.get_absolute_url())
        self.assertEqual(resp.status_code, 200)

    def test_assigned_technician_can_view_and_update(self):
        self.wo.assigned_technician = self.technician
        self.wo.save()
        self.client.login(username="tech", password="pw")
        resp = self.client.get(self.wo.get_absolute_url())
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(
            reverse("shop:workorder_add_labor", args=[self.wo.pk]),
            {"description": "Diag", "hours": 1, "rate": 90},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.wo.labor_lines.count(), 1)

    def test_unassigned_technician_gets_403(self):
        self.wo.assigned_technician = self.technician
        self.wo.save()
        self.client.login(username="tech2", password="pw")
        resp = self.client.get(self.wo.get_absolute_url())
        self.assertEqual(resp.status_code, 403)

    def test_technician_cannot_reassign_technician(self):
        self.client.login(username="tech", password="pw")
        resp = self.client.post(
            reverse("shop:workorder_assign_technician", args=[self.wo.pk]), {"technician": self.technician.pk}
        )
        self.assertEqual(resp.status_code, 403)

    def test_customer_portal_no_login_required(self):
        resp = self.client.get(self.wo.get_portal_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Noise")


class CustomerLoginCreationTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane Smith")

    def test_creates_login_with_unique_username(self):
        self.client.post(reverse("shop:customer_create_login", args=[self.customer.pk]))
        self.customer.refresh_from_db()
        self.assertIsNotNone(self.customer.user)
        self.assertFalse(self.customer.user.is_staff)
        self.assertEqual(self.customer.user.username, "jane-smith")

    def test_second_customer_same_name_gets_unique_username(self):
        other = Customer.objects.create(name="Jane Smith")
        self.client.post(reverse("shop:customer_create_login", args=[self.customer.pk]))
        self.client.post(reverse("shop:customer_create_login", args=[other.pk]))
        self.customer.refresh_from_db()
        other.refresh_from_db()
        self.assertNotEqual(self.customer.user.username, other.user.username)


class CustomerDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="jane", password="pw")
        self.customer = Customer.objects.create(name="Jane", user=self.user)
        self.vehicle = make_vehicle()
        self.vehicle.owner = self.customer
        self.vehicle.save()

    def test_customer_redirected_from_main_dashboard(self):
        self.client.login(username="jane", password="pw")
        resp = self.client.get(reverse("dashboard"))
        self.assertRedirects(resp, reverse("shop:customer_dashboard"))

    def test_dashboard_shows_own_vehicle(self):
        self.client.login(username="jane", password="pw")
        resp = self.client.get(reverse("shop:customer_dashboard"))
        self.assertContains(resp, "Civic")

    def test_unlinked_account_redirected_with_error(self):
        User.objects.create_user(username="orphan", password="pw")
        self.client.login(username="orphan", password="pw")
        resp = self.client.get(reverse("shop:customer_dashboard"))
        self.assertRedirects(resp, reverse("dashboard"))


class TechnicianDashboardTests(TestCase):
    def test_technician_redirected_from_main_dashboard(self):
        user = User.objects.create_user(username="bob", password="pw")
        Technician.objects.create(user=user, name="Bob")
        self.client.login(username="bob", password="pw")
        resp = self.client.get(reverse("dashboard"))
        self.assertRedirects(resp, reverse("shop:technician_dashboard"))

    def test_dashboard_shows_only_assigned_work_orders(self):
        user = User.objects.create_user(username="bob", password="pw")
        tech = Technician.objects.create(user=user, name="Bob")
        vehicle = make_vehicle()
        customer = Customer.objects.create(name="Jane")
        assigned = WorkOrder.objects.create(customer=customer, vehicle=vehicle, complaint="mine", assigned_technician=tech)
        unassigned = WorkOrder.objects.create(customer=customer, vehicle=vehicle, complaint="not mine")

        self.client.login(username="bob", password="pw")
        resp = self.client.get(reverse("shop:technician_dashboard"))
        self.assertContains(resp, f"WO#{assigned.pk}")
        self.assertNotContains(resp, f"WO#{unassigned.pk}")


class EstimateFlowTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.vehicle.owner = self.customer
        self.vehicle.save()

    def test_full_lifecycle_send_approve_convert(self):
        resp = self.client.post(
            reverse("shop:estimate_create", args=[self.customer.pk]),
            {"vehicle": self.vehicle.pk, "notes": "Brake job"},
        )
        estimate = Estimate.objects.get()
        self.assertEqual(estimate.status, "draft")

        self.client.post(reverse("shop:estimate_add_labor", args=[estimate.pk]), {"description": "Pads", "hours": 1, "rate": 90})
        self.client.post(reverse("shop:estimate_send", args=[estimate.pk]))
        estimate.refresh_from_db()
        self.assertEqual(estimate.status, "sent")

        self.client.logout()
        portal_url = estimate.get_portal_url()
        resp = self.client.post(portal_url, {"decision": "approve"})
        estimate.refresh_from_db()
        self.assertEqual(estimate.status, "approved")
        self.assertIsNotNone(estimate.responded_at)

        self.client.login(username="staff", password="pw")
        resp = self.client.post(reverse("shop:estimate_convert", args=[estimate.pk]))
        estimate.refresh_from_db()
        self.assertEqual(estimate.status, "converted")
        self.assertIsNotNone(estimate.work_order)
        self.assertEqual(estimate.work_order.labor_lines.count(), 1)
        self.assertEqual(estimate.work_order.labor_lines.first().description, "Pads")

    def test_decline_sets_status(self):
        estimate = Estimate.objects.create(customer=self.customer, vehicle=self.vehicle, status="sent")
        self.client.logout()
        self.client.post(estimate.get_portal_url(), {"decision": "decline"})
        estimate.refresh_from_db()
        self.assertEqual(estimate.status, "declined")

    def test_signature_stored_on_approval(self):
        estimate = Estimate.objects.create(customer=self.customer, vehicle=self.vehicle, status="sent")
        self.client.logout()
        sig = "data:image/png;base64,abc123"
        self.client.post(estimate.get_portal_url(), {"decision": "approve", "signature_data": sig})
        estimate.refresh_from_db()
        self.assertEqual(estimate.signature_data, sig)

    def test_non_image_signature_rejected(self):
        estimate = Estimate.objects.create(customer=self.customer, vehicle=self.vehicle, status="sent")
        self.client.logout()
        self.client.post(estimate.get_portal_url(), {"decision": "approve", "signature_data": "<script>evil</script>"})
        estimate.refresh_from_db()
        self.assertEqual(estimate.signature_data, "")

    def test_cannot_convert_declined_estimate(self):
        estimate = Estimate.objects.create(customer=self.customer, vehicle=self.vehicle, status="declined")
        self.client.post(reverse("shop:estimate_convert", args=[estimate.pk]))
        estimate.refresh_from_db()
        self.assertEqual(estimate.status, "declined")
        self.assertIsNone(estimate.work_order)


class AppointmentTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.vehicle.owner = self.customer
        self.vehicle.save()

    def test_create_appointment(self):
        resp = self.client.post(
            reverse("shop:appointment_create"),
            {
                "customer": self.customer.pk,
                "vehicle": self.vehicle.pk,
                "date": "2026-12-01",
                "time": "10:00",
                "duration_minutes": 60,
                "reason": "Brake inspection",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(Appointment.objects.get().reason, "Brake inspection")

    def test_invalid_datetime_shows_error(self):
        resp = self.client.post(
            reverse("shop:appointment_create"),
            {"customer": self.customer.pk, "date": "not-a-date", "time": "10:00", "reason": "x"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_start_work_order_from_appointment(self):
        appt = Appointment.objects.create(
            customer=self.customer, vehicle=self.vehicle, scheduled_at="2026-12-01T10:00Z", reason="Oil change"
        )
        resp = self.client.post(reverse("shop:appointment_start_work_order", args=[appt.pk]))
        appt.refresh_from_db()
        self.assertIsNotNone(appt.work_order)
        self.assertEqual(appt.status, "completed")
        self.assertEqual(appt.work_order.complaint, "Oil change")


class InventoryTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Brakes")
        self.part = InventoryPart.objects.create(
            part_number="BP-100", description="Brake Pad Set", quantity_on_hand=5, reorder_point=2, default_price=45
        )

    def test_adding_part_from_inventory_decrements_stock(self):
        self.client.post(
            reverse("shop:workorder_add_part", args=[self.wo.pk]),
            {"inventory_part": self.part.pk, "quantity": 2},
        )
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantity_on_hand, 3)
        line = self.wo.part_lines.get()
        self.assertEqual(line.part_number, "BP-100")
        self.assertEqual(line.unit_price, Decimal("45"))

    def test_manual_part_entry_does_not_touch_inventory(self):
        self.client.post(
            reverse("shop:workorder_add_part", args=[self.wo.pk]),
            {"part_number": "XYZ", "description": "Generic part", "quantity": 1, "unit_price": 10},
        )
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantity_on_hand, 5)

    def test_is_low_stock_property(self):
        self.part.quantity_on_hand = 2
        self.part.save()
        self.assertTrue(self.part.is_low_stock)
        self.part.quantity_on_hand = 3
        self.part.save()
        self.assertFalse(self.part.is_low_stock)


class InspectionTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Checkup")

    def test_create_inspection_seeds_default_items(self):
        resp = self.client.post(reverse("shop:inspection_create", args=[self.wo.pk]))
        inspection = Inspection.objects.get()
        self.assertGreater(inspection.items.count(), 5)

    def test_flagging_item_and_creating_estimate(self):
        self.client.post(reverse("shop:inspection_create", args=[self.wo.pk]))
        inspection = Inspection.objects.get()
        item = inspection.items.first()
        self.client.post(
            reverse("shop:inspection_item_update", args=[item.pk]), {"status": "red", "notes": "Worn"}
        )
        item.refresh_from_db()
        self.assertEqual(item.status, "red")

        resp = self.client.post(reverse("shop:inspection_create_estimate", args=[inspection.pk]))
        estimate = Estimate.objects.get()
        self.assertIn(item.description, estimate.notes)
        self.assertIn("Worn", estimate.notes)

    def test_green_items_excluded_from_estimate_notes(self):
        self.client.post(reverse("shop:inspection_create", args=[self.wo.pk]))
        inspection = Inspection.objects.get()
        green_item = inspection.items.first()
        self.client.post(reverse("shop:inspection_create_estimate", args=[inspection.pk]))
        estimate = Estimate.objects.get()
        self.assertNotIn(green_item.description, estimate.notes)

    def test_inspection_portal_public_access(self):
        self.client.post(reverse("shop:inspection_create", args=[self.wo.pk]))
        inspection = Inspection.objects.get()
        self.client.logout()
        resp = self.client.get(inspection.get_portal_url())
        self.assertEqual(resp.status_code, 200)


class ActivityLogTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Noise")

    def test_status_change_logged(self):
        self.client.post(reverse("shop:workorder_update_status", args=[self.wo.pk]), {"status": "in_progress"})
        resp = self.client.get(reverse("shop:activity_log"))
        self.assertContains(resp, f"WO#{self.wo.pk}")
        self.assertContains(resp, "in_progress")

    def test_completing_status_sets_completed_at(self):
        self.assertIsNone(self.wo.completed_at)
        self.client.post(reverse("shop:workorder_update_status", args=[self.wo.pk]), {"status": "completed"})
        self.wo.refresh_from_db()
        self.assertIsNotNone(self.wo.completed_at)

    def test_completed_at_not_overwritten_on_repeat_save(self):
        self.client.post(reverse("shop:workorder_update_status", args=[self.wo.pk]), {"status": "completed"})
        self.wo.refresh_from_db()
        first_completed_at = self.wo.completed_at
        self.client.post(reverse("shop:workorder_update_status", args=[self.wo.pk]), {"status": "closed"})
        self.wo.refresh_from_db()
        self.assertEqual(self.wo.completed_at, first_completed_at)

    def test_customer_creation_logged(self):
        self.client.post(reverse("shop:customer_create"), {"name": "New Customer", "phone": "", "email": "", "address": ""})
        resp = self.client.get(reverse("shop:activity_log"))
        self.assertContains(resp, "Created customer")


class PDFExportTests(TestCase):
    """PDF generation depends on xhtml2pdf/python-bidi, which may be
    unavailable in some environments (e.g. a native-DLL restriction). These
    tests verify the view's own logic and skip cleanly if the dependency
    genuinely cannot be imported here, rather than failing the whole suite."""

    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Noise")
        LaborLine.objects.create(work_order=self.wo, description="Diag", hours=1, rate=90)

    def _xhtml2pdf_available(self):
        try:
            import xhtml2pdf.pisa  # noqa: F401
            return True
        except Exception:
            return False

    def test_workorder_pdf_returns_pdf(self):
        if not self._xhtml2pdf_available():
            self.skipTest("xhtml2pdf/python-bidi not importable in this environment")
        resp = self.client.get(reverse("shop:workorder_pdf", args=[self.wo.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_pdf_requires_staff(self):
        self.client.logout()
        resp = self.client.get(reverse("shop:workorder_pdf", args=[self.wo.pk]))
        self.assertEqual(resp.status_code, 302)


class InvoiceAndPaymentTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Brakes")
        LaborLine.objects.create(work_order=self.wo, description="Labor", hours=1, rate=Decimal("100"))

    def test_create_invoice_from_work_order(self):
        resp = self.client.post(reverse("shop:workorder_create_invoice", args=[self.wo.pk]))
        self.wo.refresh_from_db()
        self.assertEqual(self.wo.status, "invoiced")
        self.assertTrue(hasattr(self.wo, "invoice"))
        self.assertEqual(resp.status_code, 302)

    def test_cannot_create_second_invoice(self):
        self.client.post(reverse("shop:workorder_create_invoice", args=[self.wo.pk]))
        invoice_id_first = self.wo.invoice.pk
        self.client.post(reverse("shop:workorder_create_invoice", args=[self.wo.pk]))
        self.wo.refresh_from_db()
        self.assertEqual(self.wo.invoice.pk, invoice_id_first)
        self.assertEqual(Invoice.objects.filter(work_order=self.wo).count(), 1)

    def test_payment_reduces_balance_and_marks_paid(self):
        self.client.post(reverse("shop:workorder_create_invoice", args=[self.wo.pk]))
        invoice = self.wo.invoice
        self.assertEqual(invoice.balance_due, Decimal("100.00"))

        self.client.post(
            reverse("shop:invoice_add_payment", args=[invoice.pk]), {"amount": "60", "method": "cash"}
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal("60.00"))
        self.assertEqual(invoice.balance_due, Decimal("40.00"))
        self.assertFalse(invoice.paid)

        self.client.post(
            reverse("shop:invoice_add_payment", args=[invoice.pk]), {"amount": "40", "method": "card"}
        )
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_fully_paid)
        self.assertTrue(invoice.paid)

    def test_export_csv_contains_invoice(self):
        self.client.post(reverse("shop:workorder_create_invoice", args=[self.wo.pk]))
        resp = self.client.get(reverse("shop:export_invoices_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        body = resp.content.decode()
        self.assertIn(self.wo.invoice.invoice_number, body)


class TaxExemptToggleTests(TestCase):
    def test_toggle_flips_and_persists(self):
        make_staff()
        client_login_ok = self.client.login(username="staff", password="pw")
        self.assertTrue(client_login_ok)
        customer = Customer.objects.create(name="Jane")
        self.assertFalse(customer.tax_exempt)
        self.client.post(reverse("shop:customer_toggle_tax_exempt", args=[customer.pk]))
        customer.refresh_from_db()
        self.assertTrue(customer.tax_exempt)
        self.client.post(reverse("shop:customer_toggle_tax_exempt", args=[customer.pk]))
        customer.refresh_from_db()
        self.assertFalse(customer.tax_exempt)


class TimeClockTests(TestCase):
    def setUp(self):
        self.tech_user = User.objects.create_user(username="bob", password="pw")
        self.technician = Technician.objects.create(user=self.tech_user, name="Bob")
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.wo = WorkOrder.objects.create(
            customer=self.customer, vehicle=self.vehicle, complaint="Brakes", assigned_technician=self.technician
        )
        self.client.login(username="bob", password="pw")

    def test_clock_in_creates_active_entry(self):
        self.client.post(reverse("shop:workorder_clock_in", args=[self.wo.pk]))
        entry = TimeEntry.objects.get(work_order=self.wo, technician=self.technician)
        self.assertTrue(entry.is_active)

    def test_clock_in_twice_does_not_duplicate(self):
        self.client.post(reverse("shop:workorder_clock_in", args=[self.wo.pk]))
        self.client.post(reverse("shop:workorder_clock_in", args=[self.wo.pk]))
        self.assertEqual(TimeEntry.objects.filter(work_order=self.wo, technician=self.technician).count(), 1)

    def test_clock_out_closes_entry(self):
        self.client.post(reverse("shop:workorder_clock_in", args=[self.wo.pk]))
        self.client.post(reverse("shop:workorder_clock_out", args=[self.wo.pk]))
        entry = TimeEntry.objects.get(work_order=self.wo, technician=self.technician)
        self.assertFalse(entry.is_active)
        self.assertIsNotNone(entry.clock_out)

    def test_unassigned_technician_cannot_clock_in(self):
        other_user = User.objects.create_user(username="alice", password="pw")
        Technician.objects.create(user=other_user, name="Alice")
        self.client.logout()
        self.client.login(username="alice", password="pw")
        resp = self.client.post(reverse("shop:workorder_clock_in", args=[self.wo.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_customer_cannot_clock_in(self):
        cust_user = User.objects.create_user(username="cust", password="pw")
        Customer.objects.create(name="Someone", user=cust_user)
        self.client.logout()
        self.client.login(username="cust", password="pw")
        resp = self.client.post(reverse("shop:workorder_clock_in", args=[self.wo.pk]))
        self.assertEqual(resp.status_code, 403)


class NotificationTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane", email="jane@example.com")
        self.vehicle = make_vehicle()
        self.vehicle.owner = self.customer
        self.vehicle.save()

    def test_appointment_creation_emails_customer(self):
        self.client.post(
            reverse("shop:appointment_create"),
            {
                "customer": self.customer.pk,
                "vehicle": self.vehicle.pk,
                "date": "2030-01-15",
                "time": "10:00",
                "reason": "Oil change",
                "duration_minutes": 60,
            },
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["jane@example.com"])
        self.assertIn("Oil change", mail.outbox[0].body)

    def test_no_email_sent_when_customer_has_none(self):
        self.customer.email = ""
        self.customer.save()
        self.client.post(
            reverse("shop:appointment_create"),
            {
                "customer": self.customer.pk,
                "date": "2030-01-15",
                "time": "10:00",
                "reason": "Oil change",
                "duration_minutes": 60,
            },
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_estimate_send_emails_customer_with_portal_link(self):
        estimate = Estimate.objects.create(customer=self.customer, vehicle=self.vehicle, status="draft")
        self.client.post(reverse("shop:estimate_send", args=[estimate.pk]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(estimate.get_portal_url(), mail.outbox[0].body)

    def test_invoice_creation_emails_customer(self):
        wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Brakes")
        self.client.post(reverse("shop:workorder_create_invoice", args=[wo.pk]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Invoice", mail.outbox[0].subject)


class CalendarFeedTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()
        self.appointment = Appointment.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            scheduled_at=timezone.now() + datetime.timedelta(days=1),
            reason="Oil change",
        )

    def test_build_ics_includes_appointment(self):
        ics = build_appointments_ics(Appointment.objects.all())
        self.assertIn("BEGIN:VEVENT", ics)
        self.assertIn("Oil change", ics)
        self.assertIn(f"UID:repairhub-appointment-{self.appointment.pk}@repair-hub", ics)

    def test_feed_requires_correct_token(self):
        settings_obj = ShopSettings.get_solo()
        good_url = reverse("shop:appointments_ics_feed", args=[settings_obj.calendar_feed_token])
        resp = self.client.get(good_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/calendar; charset=utf-8")

        import uuid

        bad_url = reverse("shop:appointments_ics_feed", args=[uuid.uuid4()])
        resp = self.client.get(bad_url)
        self.assertEqual(resp.status_code, 404)

    def test_feed_accessible_without_login(self):
        self.client.logout()
        settings_obj = ShopSettings.get_solo()
        url = reverse("shop:appointments_ics_feed", args=[settings_obj.calendar_feed_token])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_regenerate_token_changes_it(self):
        old_token = ShopSettings.get_solo().calendar_feed_token
        self.client.post(reverse("shop:regenerate_calendar_feed_token"))
        new_token = ShopSettings.get_solo().calendar_feed_token
        self.assertNotEqual(old_token, new_token)


class ReportsDashboardTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.customer = Customer.objects.create(name="Jane")
        self.vehicle = make_vehicle()

    def test_outstanding_balance_reflects_unpaid_invoices(self):
        wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Brakes")
        LaborLine.objects.create(work_order=wo, description="Pads", hours=1, rate=Decimal("100.00"))
        Invoice.objects.create(work_order=wo, invoice_number="INV-00001")
        resp = self.client.get(reverse("shop:reports"))
        self.assertEqual(resp.context["outstanding_balance"], Decimal("100.00"))

    def test_avg_repair_hours_none_without_completed_orders(self):
        resp = self.client.get(reverse("shop:reports"))
        self.assertIsNone(resp.context["avg_repair_hours"])

    def test_avg_repair_hours_computed_for_completed_orders(self):
        wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Brakes")
        wo.status = "completed"
        wo.save(update_fields=["status"])
        wo.completed_at = wo.created_at + datetime.timedelta(hours=2)
        wo.save(update_fields=["completed_at"])
        resp = self.client.get(reverse("shop:reports"))
        self.assertAlmostEqual(resp.context["avg_repair_hours"], 2.0, places=1)

    def test_top_parts_counts_quantity_used(self):
        wo = WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="Brakes")
        wo.status = "completed"
        wo.save(update_fields=["status"])
        PartLine.objects.create(work_order=wo, description="Brake Pad", quantity=Decimal("4"), unit_price=Decimal("20"))
        resp = self.client.get(reverse("shop:reports"))
        top_parts = dict(resp.context["top_parts"])
        self.assertEqual(top_parts["Brake Pad"], Decimal("4"))

    def test_revenue_by_month_has_six_entries(self):
        resp = self.client.get(reverse("shop:reports"))
        self.assertEqual(len(resp.context["revenue_by_month"]), 6)
