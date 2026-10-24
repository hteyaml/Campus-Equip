from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import AuditLog, CatalogItem, Category, EquipmentUnit, Profile


class CatalogTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin1", password="pass12345")
        Profile.objects.update_or_create(user=self.admin, defaults={"role": "ADMIN"})
        self.basic = User.objects.create_user("basic1", password="pass12345")
        Profile.objects.update_or_create(user=self.basic, defaults={"role": "BASIC_USER"})
        self.cat = Category.objects.create(name="Audio")
        self.item = CatalogItem.objects.create(category=self.cat, name="Speaker")
        self.client.login(username="admin1", password="pass12345")

    def make_unit(self, code="SPK-001", status="Available"):
        return EquipmentUnit.objects.create(
            catalog_item=self.item, asset_code=code, condition="Good",
            acquisition_date="2026-01-01", inventory_status=status)


    def test_basic_user_and_anonymous_blocked(self):
        urls = [reverse("catalog:category_list"), reverse("catalog:item_list"),
                reverse("catalog:unit_list"), reverse("catalog:unit_create")]
        self.client.logout()
        for url in urls:
            self.assertNotEqual(self.client.get(url).status_code, 200)
        self.client.login(username="basic1", password="pass12345")
        for url in urls:
            self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_duplicate_category_rejected(self):
        r = self.client.post(reverse("catalog:category_create"), {"name": "audio"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Category.objects.count(), 1)

    def test_cannot_archive_category_with_active_items(self):
        self.client.post(reverse("catalog:category_archive", args=[self.cat.pk]))
        self.cat.refresh_from_db()
        self.assertFalse(self.cat.is_archived)

    def test_archive_empty_category_logs_audit(self):
        empty = Category.objects.create(name="Empty")
        self.client.post(reverse("catalog:category_archive", args=[empty.pk]))
        empty.refresh_from_db()
        self.assertTrue(empty.is_archived)
        self.assertTrue(AuditLog.objects.filter(action="CATEGORY_ARCHIVED").exists())

    def test_get_does_not_archive(self):
        empty = Category.objects.create(name="Empty")
        self.client.get(reverse("catalog:category_archive", args=[empty.pk]))
        empty.refresh_from_db()
        self.assertFalse(empty.is_archived)

    def test_restore_requires_post(self):
        r = self.client.get(reverse("catalog:category_restore", args=[self.cat.pk]))
        self.assertEqual(r.status_code, 405)

    def test_duplicate_item_in_category_rejected(self):
        self.client.post(reverse("catalog:item_create"),
                         {"category": self.cat.pk, "name": "speaker", "description": ""})
        self.assertEqual(CatalogItem.objects.count(), 1)

    def test_cannot_archive_item_with_issued_unit(self):
        self.make_unit(status="Issued")
        self.client.post(reverse("catalog:item_archive", args=[self.item.pk]))
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_archived)

    def test_cannot_restore_item_when_category_archived(self):
        self.item.is_archived = True
        self.item.save()
        self.cat.is_archived = True
        self.cat.save()
        self.client.post(reverse("catalog:item_restore", args=[self.item.pk]))
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_archived)


    def test_new_unit_is_available_and_status_not_postable(self):
        self.client.post(reverse("catalog:unit_create"), {
            "catalog_item": self.item.pk, "asset_code": "spk-009", "condition": "Good",
            "acquisition_date": "2026-01-01", "inventory_status": "Issued"})
        unit = EquipmentUnit.objects.get(asset_code="SPK-009")
        self.assertEqual(unit.inventory_status, "Available")

    def test_duplicate_asset_code_rejected(self):
        self.make_unit("SPK-001")
        self.client.post(reverse("catalog:unit_create"), {
            "catalog_item": self.item.pk, "asset_code": "spk-001", "condition": "Good",
            "acquisition_date": "2026-01-01"})
        self.assertEqual(EquipmentUnit.objects.count(), 1)

    def test_cannot_retire_reserved_or_issued_unit(self):
        for i, status in enumerate(["Reserved", "Issued"]):
            unit = self.make_unit(f"SPK-10{i}", status)
            self.client.post(reverse("catalog:unit_retire", args=[unit.pk]))
            unit.refresh_from_db()
            self.assertEqual(unit.inventory_status, status)

    def test_retire_available_unit(self):
        unit = self.make_unit()
        self.client.post(reverse("catalog:unit_retire", args=[unit.pk]))
        unit.refresh_from_db()
        self.assertEqual(unit.inventory_status, "Retired")
        self.assertTrue(AuditLog.objects.filter(action="UNIT_RETIRED").exists())