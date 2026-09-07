import importlib
import json
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from diagnostics.models import DTCCode
from shop.models import Customer
from vehicles.models import Make, Vehicle, VehicleModel

from .models import Favorite

User = get_user_model()


def make_staff(username="staff"):
    return User.objects.create_user(username=username, password="pw", is_staff=True)


def make_vehicle():
    make = Make.objects.create(name="Honda")
    model = VehicleModel.objects.create(make=make, name="Civic")
    return Vehicle.objects.create(year=2018, make=make, model=model)


class StaffRequiredDecoratorTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.customer_user = User.objects.create_user(username="cust", password="pw")
        Customer.objects.create(name="Jane", user=self.customer_user)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("vehicles:list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_non_staff_gets_403(self):
        self.client.login(username="cust", password="pw")
        resp = self.client.get(reverse("vehicles:list"))
        self.assertEqual(resp.status_code, 403)

    def test_staff_gets_200(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.get(reverse("vehicles:list"))
        self.assertEqual(resp.status_code, 200)

    def test_customer_cannot_reach_customer_list(self):
        self.client.login(username="cust", password="pw")
        resp = self.client.get(reverse("shop:customer_list"))
        self.assertEqual(resp.status_code, 403)


class FavoriteTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.vehicle = make_vehicle()
        self.client.login(username="staff", password="pw")

    def test_toggle_creates_and_deletes_favorite(self):
        ct = ContentType.objects.get_for_model(Vehicle)
        url = reverse("toggle_favorite")

        self.client.post(url, {"content_type_id": ct.pk, "object_id": self.vehicle.pk, "next": "/vehicles/1/"})
        self.assertTrue(
            Favorite.objects.filter(user=self.staff, content_type=ct, object_id=self.vehicle.pk).exists()
        )

        self.client.post(url, {"content_type_id": ct.pk, "object_id": self.vehicle.pk, "next": "/vehicles/1/"})
        self.assertFalse(
            Favorite.objects.filter(user=self.staff, content_type=ct, object_id=self.vehicle.pk).exists()
        )

    def test_favorites_list_shows_favorited_vehicle(self):
        ct = ContentType.objects.get_for_model(Vehicle)
        Favorite.objects.create(user=self.staff, content_type=ct, object_id=self.vehicle.pk)
        resp = self.client.get(reverse("favorites"))
        self.assertContains(resp, str(self.vehicle))


class GlobalSearchTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username="staff", password="pw")
        self.vehicle = make_vehicle()
        Customer.objects.create(name="Jane Smith")
        DTCCode.objects.create(code="P0300", system="P", description="Random Misfire Detected")

    def test_search_finds_customer(self):
        resp = self.client.get(reverse("global_search"), {"q": "Jane"})
        self.assertContains(resp, "Jane Smith")

    def test_search_finds_dtc_code(self):
        resp = self.client.get(reverse("global_search"), {"q": "P0300"})
        self.assertContains(resp, "P0300")

    def test_search_finds_vehicle(self):
        resp = self.client.get(reverse("global_search"), {"q": "Civic"})
        self.assertContains(resp, "Civic")

    def test_empty_query_shows_no_results_section(self):
        resp = self.client.get(reverse("global_search"))
        self.assertEqual(resp.status_code, 200)


class BackupDownloadTests(TestCase):
    def setUp(self):
        make_staff()
        make_vehicle()

    def test_requires_staff(self):
        resp = self.client.get(reverse("download_backup"))
        self.assertEqual(resp.status_code, 302)

    def test_returns_valid_json_dump(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.get(reverse("download_backup"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/json")
        data = json.loads(resp.content)
        self.assertIsInstance(data, list)
        models_present = {row["model"] for row in data}
        self.assertIn("vehicles.vehicle", models_present)


class AllowedHostsDefaultTests(TestCase):
    """Regression test for GitHub issue #1: fresh Unraid installs got a
    400 Bad Request because ALLOWED_HOSTS defaulted to localhost/127.0.0.1
    only, which rejects the LAN-IP host header Unraid users actually hit.
    """

    def test_defaults_to_wildcard_when_unset(self):
        from repairhub import settings as settings_module

        env = dict(os.environ)
        env.pop("DJANGO_ALLOWED_HOSTS", None)
        with mock.patch.dict(os.environ, env, clear=True):
            importlib.reload(settings_module)
            try:
                self.assertEqual(settings_module.ALLOWED_HOSTS, ["*"])
            finally:
                importlib.reload(settings_module)

    def test_explicit_hosts_still_respected(self):
        from repairhub import settings as settings_module

        env = dict(os.environ)
        env["DJANGO_ALLOWED_HOSTS"] = "192.168.1.50,repairhub.local"
        with mock.patch.dict(os.environ, env, clear=True):
            importlib.reload(settings_module)
            try:
                self.assertEqual(
                    settings_module.ALLOWED_HOSTS,
                    ["192.168.1.50", "repairhub.local"],
                )
                self.assertIn(
                    "http://192.168.1.50", settings_module.CSRF_TRUSTED_ORIGINS
                )
            finally:
                importlib.reload(settings_module)
