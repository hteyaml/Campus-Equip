from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from inventory.models import Profile, Category, CatalogItem, EquipmentUnit
import random
from datetime import date, timedelta


class Command(BaseCommand):
    help = 'Seeds the database with required demonstration data'

    def handle(self, *args, **kwargs):
        self.stdout.write("Clearing old data...")
        User.objects.all().delete()
        Category.objects.all().delete()

        self.stdout.write("Creating 1 Admin and 8 Basic Users...")
        # Create Admin
        admin_user = User.objects.create_superuser('admin_tester', 'admin@bulsu.edu.ph', 'password123')
        Profile.objects.create(user=admin_user, role='ADMIN')

        # Create Basic Users using fictional identities
        users = []
        for i in range(1, 9):
            u = User.objects.create_user(f'student{i}', f'student{i}@bulsu.edu.ph', 'password123')
            Profile.objects.create(user=u, role='BASIC_USER', contact_number=f'0912345678{i}')
            users.append(u)

        self.stdout.write("Creating 3 Categories and 6 Catalog Items...")
        cat_electronics = Category.objects.create(name='Electronics', description='Laptops and tablets')
        cat_av = Category.objects.create(name='Audio/Visual', description='Cameras and projectors')
        cat_network = Category.objects.create(name='Networking', description='Routers and switches')

        items = [
            CatalogItem.objects.create(category=cat_electronics, name='Dell XPS 15',
                                       description='High performance laptop'),
            CatalogItem.objects.create(category=cat_electronics, name='iPad Pro',
                                       description='Tablet for presentations'),
            CatalogItem.objects.create(category=cat_av, name='Sony A7III', description='Mirrorless camera'),
            CatalogItem.objects.create(category=cat_av, name='Epson Projector', description='1080p projector'),
            CatalogItem.objects.create(category=cat_network, name='Cisco Router', description='Enterprise router'),
            CatalogItem.objects.create(category=cat_network, name='Netgear Switch',
                                       description='24-port gigabit switch'),
        ]

        self.stdout.write("Creating 18 Physical Units...")
        statuses = ['Available', 'Reserved', 'Issued', 'Maintenance', 'Retired']

        # Distribute 18 units across the 6 items (3 units each)
        unit_count = 1
        for item in items:
            for _ in range(3):
                EquipmentUnit.objects.create(
                    catalog_item=item,
                    asset_code=f'ASSET-{unit_count:04d}',
                    condition='Good',
                    acquisition_date=date.today() - timedelta(days=random.randint(10, 365)),
                    inventory_status='Available'  # Start available, update when seeding requests
                )
                unit_count += 1

        self.stdout.write(self.style.SUCCESS("Successfully seeded baseline data!"))
        self.stdout.write("Next step: Add scripts for the 20 requests, 8 loans, and 4 maintenance records.")