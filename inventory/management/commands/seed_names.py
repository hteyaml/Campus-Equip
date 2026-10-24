from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Populates first and last names for existing test user accounts.'

    def handle(self, *args, **kwargs):
        user_data = {
            'student1': ('Alice', 'Smith'),
            'student2': ('Brian', 'Johnson'),
            'student3': ('Chloe', 'Williams'),
            'student4': ('Daniel', 'Brown'),
            'student5': ('Emma', 'Jones'),
            'student6': ('Felix', 'Garcia'),
            'student7': ('Grace', 'Miller'),
            'student8': ('Henry', 'Davis'),
        }

        self.stdout.write("Starting database name update...")
        updated_count = 0

        for username, (first_name, last_name) in user_data.items():
            try:
                user = User.objects.get(username=username)
                user.first_name = first_name
                user.last_name = last_name
                user.save()
                self.stdout.write(self.style.SUCCESS(f"✅ Updated {username} -> {first_name} {last_name}"))
                updated_count += 1
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"⚠️ User '{username}' does not exist in the database. Skipping."))

        self.stdout.write(self.style.SUCCESS(f"\nUpdate complete! {updated_count} accounts modified."))