import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .importers import DTCImportError, import_dtc_codes_from_csv
from .models import DTCCode

User = get_user_model()


class SeedCommandTests(TestCase):
    def test_seed_creates_generic_codes(self):
        call_command("seed_dtc_codes")
        self.assertGreater(DTCCode.objects.count(), 100)
        self.assertTrue(DTCCode.objects.filter(code="P0300").exists())

    def test_seed_is_idempotent(self):
        call_command("seed_dtc_codes")
        first_count = DTCCode.objects.count()
        call_command("seed_dtc_codes")
        self.assertEqual(DTCCode.objects.count(), first_count)


class ImportCSVTests(TestCase):
    def test_import_creates_codes(self):
        csv_data = "code,description,system,origin,make\nP1130,Toyota Fuel Trim,P,manufacturer,Toyota\n"
        stats = import_dtc_codes_from_csv(io.StringIO(csv_data))
        self.assertEqual(stats["created"], 1)
        code = DTCCode.objects.get(code="P1130")
        self.assertEqual(code.make.name, "Toyota")
        self.assertEqual(code.origin, "manufacturer")

    def test_import_updates_existing_code(self):
        DTCCode.objects.create(code="P1130", description="Old description", system="P")
        csv_data = "code,description,system,origin,make\nP1130,New description,P,generic,\n"
        stats = import_dtc_codes_from_csv(io.StringIO(csv_data))
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(DTCCode.objects.get(code="P1130").description, "New description")

    def test_missing_required_columns_raises(self):
        with self.assertRaises(DTCImportError):
            import_dtc_codes_from_csv(io.StringIO("foo,bar\n1,2\n"))

    def test_system_auto_derived_from_code_prefix(self):
        csv_data = "code,description\nB1318,Battery Voltage Low\n"
        import_dtc_codes_from_csv(io.StringIO(csv_data))
        self.assertEqual(DTCCode.objects.get(code="B1318").system, "B")


class ViewAccessTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff", password="pw", is_staff=True)
        DTCCode.objects.create(code="P0300", description="Random Misfire Detected", system="P")

    def test_anonymous_redirected(self):
        resp = self.client.get(reverse("diagnostics:list"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_can_search(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.get(reverse("diagnostics:list"), {"q": "P0300"})
        self.assertContains(resp, "P0300")

    def test_detail_view_case_insensitive(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.get(reverse("diagnostics:detail", args=["p0300"]))
        self.assertEqual(resp.status_code, 200)

    def test_import_requires_staff(self):
        tech_user = User.objects.create_user(username="tech", password="pw")
        from shop.models import Technician

        Technician.objects.create(user=tech_user, name="Bob")
        self.client.login(username="tech", password="pw")
        resp = self.client.get(reverse("diagnostics:import"))
        self.assertEqual(resp.status_code, 403)
