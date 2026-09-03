from unittest.mock import Mock, patch
import requests

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from diagnostics.models import DTCCode

from .external import search_commons_images, search_ifixit
from .importers import GuideImportError, import_guides_from_records
from .models import RepairGuide

User = get_user_model()


class ImportGuidesTests(TestCase):
    def test_creates_guide_with_steps_and_dtc_codes(self):
        DTCCode.objects.create(code="P0420", description="Catalyst efficiency", system="P")
        records = [
            {
                "title": "Brake pad replacement",
                "system": "Brakes",
                "make": "Honda",
                "model": "Civic",
                "summary": "Replace pads",
                "dtc_codes": ["P0420"],
                "steps": [
                    {"order": 1, "instructions": "Raise vehicle", "torque_spec": "", "caution": ""},
                    {"order": 2, "instructions": "Remove caliper", "torque_spec": "27 ft-lb", "caution": ""},
                ],
            }
        ]
        stats = import_guides_from_records(records)
        self.assertEqual(stats["created"], 1)
        guide = RepairGuide.objects.get(title="Brake pad replacement")
        self.assertEqual(guide.steps.count(), 2)
        self.assertEqual(guide.dtc_codes.count(), 1)
        self.assertEqual(guide.make.name, "Honda")

    def test_skips_existing_guide_without_update_flag(self):
        records = [{"title": "Oil change", "system": "Engine", "steps": []}]
        import_guides_from_records(records)
        stats = import_guides_from_records(records)
        self.assertEqual(stats["created"], 0)
        self.assertEqual(len(stats["skipped"]), 1)

    def test_update_flag_replaces_steps(self):
        records = [
            {
                "title": "Oil change",
                "system": "Engine",
                "steps": [{"order": 1, "instructions": "Old step"}],
            }
        ]
        import_guides_from_records(records)
        records[0]["steps"] = [{"order": 1, "instructions": "New step"}]
        stats = import_guides_from_records(records, update=True)
        self.assertEqual(stats["updated"], 1)
        guide = RepairGuide.objects.get(title="Oil change")
        self.assertEqual(guide.steps.count(), 1)
        self.assertEqual(guide.steps.first().instructions, "New step")

    def test_missing_title_or_system_is_skipped(self):
        stats = import_guides_from_records([{"title": "No system here"}])
        self.assertEqual(stats["created"], 0)
        self.assertEqual(len(stats["skipped"]), 1)

    def test_non_list_input_raises(self):
        with self.assertRaises(GuideImportError):
            import_guides_from_records({"not": "a list"})


class ExternalSearchTests(TestCase):
    @patch("repairguides.external.requests.get")
    def test_search_ifixit_parses_results(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "results": [
                    {
                        "title": "Brake Pad Replacement",
                        "summary": "How to replace brake pads",
                        "url": "https://www.ifixit.com/Guide/x/1",
                        "image": {"thumbnail": "https://x/thumb.jpg"},
                    }
                ]
            },
        )
        mock_get.return_value.raise_for_status = lambda: None
        results = search_ifixit("brake pads")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "iFixit")

    def test_empty_query_returns_empty_list(self):
        self.assertEqual(search_ifixit(""), [])
        self.assertEqual(search_commons_images(""), [])

    @patch("repairguides.external.requests.get", side_effect=requests.RequestException("network down"))
    def test_graceful_on_network_failure(self, mock_get):
        self.assertEqual(search_ifixit("brakes"), [])


class ViewAccessTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff", password="pw", is_staff=True)

    def test_import_requires_staff(self):
        anon_resp = self.client.get(reverse("repairguides:import"))
        self.assertEqual(anon_resp.status_code, 302)

    def test_guide_list_requires_login(self):
        resp = self.client.get(reverse("repairguides:list"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_can_view_guide_list(self):
        self.client.login(username="staff", password="pw")
        resp = self.client.get(reverse("repairguides:list"))
        self.assertEqual(resp.status_code, 200)
