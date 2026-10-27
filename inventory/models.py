from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator

class Profile(models.Model):
    ROLE_CHOICES = [('BASIC_USER', 'Basic User'), ('ADMIN', 'Admin')]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default='BASIC_USER')
    contact_number = models.CharField(max_length=20, blank=True, null=True)

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    is_archived = models.BooleanField(default=False)

class CatalogItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.RESTRICT)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    is_archived = models.BooleanField(default=False)

class EquipmentUnit(models.Model):
    STATUS_CHOICES = [
        ('Available', 'Available'),
        ('Reserved', 'Reserved'),
        ('Issued', 'Issued'),
        ('Maintenance', 'Maintenance'),
        ('Retired', 'Retired'),
    ]
    catalog_item = models.ForeignKey(CatalogItem, on_delete=models.RESTRICT)
    asset_code = models.CharField(max_length=50, unique=True)
    condition = models.CharField(max_length=255)
    acquisition_date = models.DateField()
    inventory_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Available')


class BorrowRequest(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'), ('Approved', 'Approved'),
        ('Issued', 'Issued'), ('Rejected', 'Rejected'), ('Cancelled', 'Cancelled')
    ]
    owner = models.ForeignKey(User, on_delete=models.RESTRICT)
    item = models.ForeignKey(CatalogItem, on_delete=models.RESTRICT, null=True, blank=True)

    equipment_unit = models.ForeignKey(EquipmentUnit, on_delete=models.RESTRICT, null=True, blank=True)

    request_date = models.DateTimeField(auto_now_add=True)
    desired_return_date = models.DateField()
    workflow_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    purpose = models.TextField(blank=True, null=True)


class RequestItem(models.Model):
    borrow_request = models.ForeignKey(BorrowRequest, on_delete=models.CASCADE)
    catalog_item = models.ForeignKey(CatalogItem, on_delete=models.RESTRICT)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])

    class Meta:
        # Validates that an item is only listed once per request
        unique_together = ('borrow_request', 'catalog_item')

class UnitAllocation(models.Model):
    request_item = models.ForeignKey(RequestItem, on_delete=models.CASCADE)
    unit = models.ForeignKey(EquipmentUnit, on_delete=models.RESTRICT)
    allocation_timestamp = models.DateTimeField(auto_now_add=True)
    is_released = models.BooleanField(default=False)
    is_cancelled = models.BooleanField(default=False)

class Loan(models.Model):
    borrow_request = models.OneToOneField(BorrowRequest, on_delete=models.RESTRICT)
    issue_actor = models.ForeignKey(User, on_delete=models.RESTRICT)
    issue_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField()

class ReturnRecord(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    unit = models.ForeignKey(EquipmentUnit, on_delete=models.RESTRICT)
    return_date = models.DateTimeField(auto_now_add=True)
    return_condition = models.CharField(max_length=255)

class MaintenanceRecord(models.Model):
    unit = models.ForeignKey(EquipmentUnit, on_delete=models.RESTRICT)
    problem = models.TextField()
    action_taken = models.TextField(blank=True, null=True)
    date_opened = models.DateField(auto_now_add=True)
    date_closed = models.DateField(blank=True, null=True)
    responsible_admin = models.ForeignKey(User, on_delete=models.RESTRICT)
    status = models.CharField(max_length=50, default='Open')

class AuditLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    record_reference = models.CharField(max_length=255)


class SystemSettings(models.Model):
    max_loan_duration_days = models.IntegerField(default=7)
    max_quantity_per_item = models.IntegerField(default=3)

    def save(self, *args, **kwargs):
        # Force the ID to always be 1 so we never create duplicate settings rows
        self.pk = 1
        super(SystemSettings, self).save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "System Settings"