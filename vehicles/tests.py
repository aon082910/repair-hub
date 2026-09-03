import datetime
from unittest.mock import Mock, patch
import requests

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from shop.models import Customer, WorkOrder

from .models import MaintenanceReminder, Make, Vehicle, VehicleModel
from .recalls import get_complaints, get_recalls
from .safety import get_safety_ratings
from .specs import find_vehicle_options
from .vin import decode_vin
from .wiki import get_model_summary

User = get_user_model()


def make_vehicle(year=2018, make_name="Honda", model_name="Civic"):
    make, _ = Make.objects.get_or_create(name=make_name)
    model, _ = VehicleModel.objects.get_or_create(make=make, name=model_name)
    return Vehicle.objects.create(year=year, make=make, model=model)


class VehicleModelTests(TestCase):
    def test_str_includes_year_make_model(self):
        v = make_vehicle()
        self.assertEqual(str(v), "2018 Honda Civic")

    def test_str_includes_trim_when_set(self):
        make, _ = Make.objects.get_or_create(name="Honda")
        model, _ = VehicleModel.objects.get_or_create(make=make, name="Civic")
        v = Vehicle.objects.create(year=2018, make=make, model=model, trim="EX")
        self.assertEqual(str(v), "2018 Honda Civic EX")

    def test_latest_odometer_returns_highest_reading(self):
        v = make_vehicle()
        c = Customer.objects.create(name="Jane")
        WorkOrder.objects.create(customer=c, vehicle=v, complaint="a", odometer=1000)
        WorkOrder.objects.create(customer=c, vehicle=v, complaint="b", odometer=5000)
        WorkOrder.objects.create(customer=c, vehicle=v, complaint="c", odometer=3000)
        self.assertEqual(v.latest_odometer(), 5000)

    def test_latest_odometer_none_when_no_work_orders(self):
        v = make_vehicle()
        self.assertIsNone(v.latest_odometer())

    def test_access_token_unique_per_vehicle(self):
        v1 = make_vehicle()
        v2 = make_vehicle(year=2019)
        self.assertNotEqual(v1.access_token, v2.access_token)


class MaintenanceReminderTests(TestCase):
    def setUp(self):
        self.vehicle = make_vehicle()

    def test_due_soon_within_30_days(self):
        r = MaintenanceReminder.objects.create(
            vehicle=self.vehicle, description="Oil change", due_date=timezone.localdate() + datetime.timedelta(days=10)
        )
        self.assertTrue(r.is_due_soon)
        self.assertFalse(r.is_overdue)

    def test_not_due_soon_when_far_out(self):
        r = MaintenanceReminder.objects.create(
            vehicle=self.vehicle, description="Oil change", due_date=timezone.localdate() + datetime.timedelta(days=90)
        )
        self.assertFalse(r.is_due_soon)

    def test_overdue_when_past_due_date(self):
        # An overdue item is also "due soon" (it's a superset check) --
        # templates decide precedence by checking is_overdue first.
        r = MaintenanceReminder.objects.create(
            vehicle=self.vehicle, description="Oil change", due_date=timezone.localdate() - datetime.timedelta(days=1)
        )
        self.assertTrue(r.is_overdue)
        self.assertTrue(r.is_due_soon)

    def test_completed_reminder_never_due_soon_or_overdue(self):
        r = MaintenanceReminder.objects.create(
            vehicle=self.vehicle,
            description="Oil change",
            due_date=timezone.localdate() - datetime.timedelta(days=1),
            completed=True,
        )
        self.assertFalse(r.is_due_soon)
        self.assertFalse(r.is_overdue)

    def test_mark_done_creates_next_occurrence_with_interval(self):
        r = MaintenanceReminder.objects.create(
            vehicle=self.vehicle,
            description="Oil change",
            due_date=timezone.localdate(),
            interval_months=6,
        )
        r.mark_done()
        r.refresh_from_db()
        self.assertTrue(r.completed)
        self.assertIsNotNone(r.completed_at)

        next_reminder = MaintenanceReminder.objects.exclude(pk=r.pk).get(vehicle=self.vehicle)
        self.assertFalse(next_reminder.completed)
        self.assertGreater(next_reminder.due_date, r.due_date)

    def test_mark_done_no_next_occurrence_without_interval(self):
        r = MaintenanceReminder.objects.create(vehicle=self.vehicle, description="One-off inspection")
        r.mark_done()
        self.assertEqual(MaintenanceReminder.objects.filter(vehicle=self.vehicle).count(), 1)

    def test_due_mileage_soon_compares_to_latest_odometer(self):
        c = Customer.objects.create(name="Jane")
        WorkOrder.objects.create(customer=c, vehicle=self.vehicle, complaint="x", odometer=29500)
        r = MaintenanceReminder.objects.create(vehicle=self.vehicle, description="Tire rotation", due_mileage=30000)
        self.assertTrue(r.is_due_soon)


class VinDecodeTests(TestCase):
    @patch("vehicles.vin.requests.get")
    def test_decode_vin_parses_response(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "Results": [
                    {
                        "ModelYear": "2018",
                        "Make": "HONDA",
                        "Model": "Civic",
                        "Trim": "EX",
                        "EngineCylinders": "4",
                        "DisplacementL": "2.0",
                        "FuelTypePrimary": "Gasoline",
                    }
                ]
            },
        )
        mock_get.return_value.raise_for_status = lambda: None
        result = decode_vin("1" * 17)
        self.assertEqual(result["year"], "2018")
        self.assertEqual(result["make"], "HONDA")

    def test_decode_vin_rejects_wrong_length(self):
        self.assertEqual(decode_vin("short"), {})

    @patch("vehicles.vin.requests.get", side_effect=requests.RequestException("network down"))
    def test_decode_vin_returns_empty_on_network_failure(self, mock_get):
        result = decode_vin("1" * 17)
        self.assertEqual(result, {})


class RecallsTests(TestCase):
    @patch("vehicles.recalls.requests.get")
    def test_get_recalls_returns_results(self, mock_get):
        mock_get.return_value = Mock(status_code=200, json=lambda: {"results": [{"Component": "BRAKES"}]})
        mock_get.return_value.raise_for_status = lambda: None
        results = get_recalls("Honda", "Civic", 2018)
        self.assertEqual(results, [{"Component": "BRAKES"}])

    def test_get_recalls_empty_without_required_fields(self):
        self.assertEqual(get_recalls("", "Civic", 2018), [])

    @patch("vehicles.recalls.requests.get", side_effect=requests.RequestException("timeout"))
    def test_get_complaints_graceful_on_failure(self, mock_get):
        self.assertEqual(get_complaints("Honda", "Civic", 2018), [])


class SpecsTests(TestCase):
    @patch("vehicles.specs._get_xml")
    def test_falls_back_to_prefix_match_when_exact_model_empty(self, mock_get_xml):
        import xml.etree.ElementTree as ET

        empty_root = ET.fromstring("<menuItems></menuItems>")
        model_list_root = ET.fromstring(
            "<menuItems><menuItem><value>Civic 4Dr</value><text>Civic 4Dr</text></menuItem></menuItems>"
        )
        options_root = ET.fromstring(
            '<menuItems><menuItem><value>123</value><text>Auto, 4cyl</text></menuItem></menuItems>'
        )

        mock_get_xml.side_effect = [empty_root, model_list_root, options_root]
        options = find_vehicle_options(2018, "Honda", "Civic")
        self.assertEqual(options, [{"id": "123", "text": "Auto, 4cyl"}])


class ViewAccessTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff", password="pw", is_staff=True)
        self.tech_user = User.objects.create_user(username="tech", password="pw")
        from shop.models import Technician

        Technician.objects.create(user=self.tech_user, name="Bob")
        self.vehicle = make_vehicle()

    def test_staff_can_view_vehicle_list(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.get(reverse("vehicles:list"))
        self.assertEqual(resp.status_code, 200)

    def test_technician_can_view_vehicle_list(self):
        self.client.login(username="tech", password="pw")
        resp = self.client.get(reverse("vehicles:list"))
        self.assertEqual(resp.status_code, 200)

    def test_vehicle_create_via_post(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.post(
            reverse("vehicles:create"),
            {"year": 2020, "make": "Toyota", "model": "Corolla", "vin": "", "trim": "", "engine": ""},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Vehicle.objects.filter(make__name="Toyota", model__name="Corolla").exists())


class ServiceHistoryTests(TestCase):
    def setUp(self):
        self.vehicle = make_vehicle()
        self.customer = Customer.objects.create(name="Jane")

    def test_no_login_required(self):
        resp = self.client.get(reverse("vehicles:service_history", args=[self.vehicle.access_token]))
        self.assertEqual(resp.status_code, 200)

    def test_only_completed_work_orders_shown(self):
        WorkOrder.objects.create(customer=self.customer, vehicle=self.vehicle, complaint="open job", status="open")
        WorkOrder.objects.create(
            customer=self.customer, vehicle=self.vehicle, complaint="finished job", status="completed"
        )
        resp = self.client.get(reverse("vehicles:service_history", args=[self.vehicle.access_token]))
        self.assertNotContains(resp, "open job")
        self.assertContains(resp, "finished job")


class QRCodeTests(TestCase):
    def test_returns_png_image(self):
        staff = User.objects.create_user(username="staff", password="pw", is_staff=True)
        self.client.login(username="staff", password="pw")
        vehicle = make_vehicle()
        resp = self.client.get(reverse("vehicles:qr_code", args=[vehicle.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")
        self.assertTrue(resp.content.startswith(b"\x89PNG"))


class SafetyRatingsTests(TestCase):
    @patch("vehicles.safety.requests.get")
    def test_fetches_ratings_via_two_step_lookup(self, mock_get):
        model_resp = Mock(status_code=200, json=lambda: {"Results": [{"VehicleId": 12636}]})
        model_resp.raise_for_status = lambda: None
        detail_resp = Mock(status_code=200, json=lambda: {"Results": [{"OverallRating": "5"}]})
        detail_resp.raise_for_status = lambda: None
        mock_get.side_effect = [model_resp, detail_resp]

        result = get_safety_ratings("Honda", "Civic", 2018)
        self.assertEqual(result, {"OverallRating": "5"})

    def test_empty_without_required_fields(self):
        self.assertEqual(get_safety_ratings("", "Civic", 2018), {})

    @patch("vehicles.safety.requests.get", side_effect=requests.RequestException("down"))
    def test_graceful_on_network_failure(self, mock_get):
        self.assertEqual(get_safety_ratings("Honda", "Civic", 2018), {})

    @patch("vehicles.safety.requests.get")
    def test_empty_when_no_matching_variant(self, mock_get):
        resp = Mock(status_code=200, json=lambda: {"Results": []})
        resp.raise_for_status = lambda: None
        mock_get.return_value = resp
        self.assertEqual(get_safety_ratings("Honda", "Civic", 2018), {})


class ModelSummaryTests(TestCase):
    @patch("vehicles.wiki.requests.get")
    def test_parses_standard_summary(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "type": "standard",
                "title": "Honda Civic",
                "extract": "The Honda Civic is a car.",
                "thumbnail": {"source": "https://x/thumb.jpg"},
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Honda_Civic"}},
            },
        )
        result = get_model_summary("Honda", "Civic")
        self.assertEqual(result["title"], "Honda Civic")
        self.assertIn("car", result["extract"])

    def test_empty_without_make_or_model(self):
        self.assertEqual(get_model_summary("", "Civic"), {})

    @patch("vehicles.wiki.requests.get")
    def test_non_standard_page_type_returns_empty(self, mock_get):
        mock_get.return_value = Mock(status_code=200, json=lambda: {"type": "disambiguation"})
        self.assertEqual(get_model_summary("Honda", "Civic"), {})

    @patch("vehicles.wiki.requests.get")
    def test_404_returns_empty(self, mock_get):
        mock_get.return_value = Mock(status_code=404)
        self.assertEqual(get_model_summary("Honda", "NonexistentModelXYZ"), {})
