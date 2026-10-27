"""
Tests for the Loan Report and Overdue Report (A5, A7).

Run with:  python manage.py test inventory.tests_reports
"""
import csv
import io
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    BorrowRequest, CatalogItem, Category, EquipmentUnit, Loan, Profile,
    RequestItem, ReturnRecord, UnitAllocation,
)
from .report_services import csv_safe, loan_status, overdue_days


class ReportTestBase(TestCase):
    """
    Four loans (all by the same borrower), today = timezone.localdate():

      A  2 units, 0 returned, due today-5   -> Issued, overdue 5 days
      B  2 units, 1 returned, due today-2   -> Partially Returned, overdue 2 days
      C  2 units, 2 returned, due today-10  -> Returned, NOT overdue
      D  1 unit,  0 returned, due today     -> Issued, NOT overdue (due date itself)
    """

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()

        cls.admin = User.objects.create_user('admin1', password='pass12345')
        Profile.objects.create(user=cls.admin, role='ADMIN')

        cls.basic = User.objects.create_user('basic1', password='pass12345')
        Profile.objects.create(user=cls.basic, role='BASIC_USER')

        cls.borrower = User.objects.create_user(
            'borrower1', password='pass12345', first_name='Ana', last_name='Cruz')
        Profile.objects.create(user=cls.borrower, role='BASIC_USER', contact_number='09123456789')

        category = Category.objects.create(name='Electronics')
        cls.item = CatalogItem.objects.create(category=category, name='Laptop')
        cls.units = [
            EquipmentUnit.objects.create(
                catalog_item=cls.item, asset_code=f'T-{i:03d}', condition='Good',
                acquisition_date=cls.today, inventory_status='Issued')
            for i in range(7)
        ]

        cls.loan_a = cls._make_loan(cls.units[0:2], due_offset=-5, returned=0)
        cls.loan_b = cls._make_loan(cls.units[2:4], due_offset=-2, returned=1)
        cls.loan_c = cls._make_loan(cls.units[4:6], due_offset=-10, returned=2)
        cls.loan_d = cls._make_loan(cls.units[6:7], due_offset=0, returned=0)

    @classmethod
    def _make_loan(cls, units, due_offset, returned):
        due = cls.today + timedelta(days=due_offset)
        req = BorrowRequest.objects.create(
            owner=cls.borrower, desired_return_date=due, workflow_status='Issued')
        req_item = RequestItem.objects.create(
            borrow_request=req, catalog_item=cls.item, quantity=len(units))
        for unit in units:
            UnitAllocation.objects.create(request_item=req_item, unit=unit, is_released=True)
        loan = Loan.objects.create(borrow_request=req, issue_actor=cls.admin, due_date=due)
        for unit in units[:returned]:
            ReturnRecord.objects.create(loan=loan, unit=unit, return_condition='Good')
        return loan

    def login_admin(self):
        self.client.force_login(self.admin)


class HelperTests(TestCase):
    def test_overdue_days_zero_on_or_before_due_date(self):
        today = timezone.localdate()
        self.assertEqual(overdue_days(today, today), 0)
        self.assertEqual(overdue_days(today + timedelta(days=3), today), 0)
        self.assertEqual(overdue_days(today - timedelta(days=4), today), 4)

    def test_loan_status(self):
        self.assertEqual(loan_status(2, 0), 'Issued')
        self.assertEqual(loan_status(2, 1), 'Partially Returned')
        self.assertEqual(loan_status(2, 2), 'Returned')

    def test_csv_safe_blocks_formula_injection(self):
        self.assertEqual(csv_safe('=SUM(A1)'), "'=SUM(A1)")
        self.assertEqual(csv_safe('+1'), "'+1")
        self.assertEqual(csv_safe('Normal text'), 'Normal text')
        self.assertEqual(csv_safe(None), '')


class AccessTests(ReportTestBase):
    def test_anonymous_is_redirected_to_login(self):
        for name in ('loan_reports_view', 'overdue_reports'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)

    def test_basic_user_is_forbidden(self):
        self.client.force_login(self.basic)
        for name in ('loan_reports_view', 'overdue_reports'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
            self.assertEqual(self.client.get(reverse(name), {'export': 'csv'}).status_code, 403)

    def test_deactivated_admin_is_blocked(self):
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        self.client.force_login(self.admin)
        self.assertNotEqual(self.client.get(reverse('loan_reports_view')).status_code, 200)


class LoanReportTests(ReportTestBase):
    def test_summary_and_statuses(self):
        self.login_admin()
        response = self.client.get(reverse('loan_reports_view'))
        self.assertEqual(response.status_code, 200)

        summary = response.context['summary']
        self.assertEqual(summary['total_loans'], 4)
        self.assertEqual(summary['units_issued'], 7)
        self.assertEqual(summary['units_returned'], 3)
        self.assertEqual(summary['units_outstanding'], 4)

        by_id = {loan.pk: loan for loan in response.context['loans']}
        self.assertEqual(by_id[self.loan_a.pk].status, 'Issued')
        self.assertEqual(by_id[self.loan_b.pk].status, 'Partially Returned')
        self.assertEqual(by_id[self.loan_c.pk].status, 'Returned')
        self.assertEqual(by_id[self.loan_d.pk].status, 'Issued')

        self.assertTrue(by_id[self.loan_a.pk].is_overdue)
        self.assertTrue(by_id[self.loan_b.pk].is_overdue)
        self.assertFalse(by_id[self.loan_c.pk].is_overdue)
        self.assertFalse(by_id[self.loan_d.pk].is_overdue)

    def test_status_filter(self):
        self.login_admin()
        expected = {'Returned': 1, 'Partially Returned': 1, 'Issued': 2}
        for status, count in expected.items():
            response = self.client.get(reverse('loan_reports_view'), {'status': status})
            self.assertEqual(response.context['summary']['total_loans'], count, status)

    def test_issue_date_filter(self):
        Loan.objects.filter(pk=self.loan_c.pk).update(
            issue_date=timezone.now() - timedelta(days=30))
        self.login_admin()
        start = (self.today - timedelta(days=1)).isoformat()
        response = self.client.get(reverse('loan_reports_view'), {'date_from': start})
        self.assertEqual(response.context['summary']['total_loans'], 3)

        end = (self.today - timedelta(days=20)).isoformat()
        response = self.client.get(reverse('loan_reports_view'), {'date_to': end})
        self.assertEqual(response.context['summary']['total_loans'], 1)

    def test_search_by_borrower_item_and_asset_code(self):
        self.login_admin()
        for term, count in (('borrower1', 4), ('Cruz', 4), ('Laptop', 4), ('T-006', 1), ('nomatch', 0)):
            response = self.client.get(reverse('loan_reports_view'), {'search': term})
            self.assertEqual(response.context['summary']['total_loans'], count, term)

    def test_search_does_not_inflate_unit_counts(self):
        self.login_admin()
        response = self.client.get(reverse('loan_reports_view'), {'search': 'Laptop'})
        self.assertEqual(response.context['summary']['units_issued'], 7)

    def test_invalid_dates_do_not_crash(self):
        self.login_admin()
        response = self.client.get(
            reverse('loan_reports_view'), {'date_from': 'abc', 'date_to': '2026-99-99'})
        self.assertEqual(response.status_code, 200)

    def test_csv_export_matches_filters(self):
        self.login_admin()
        response = self.client.get(
            reverse('loan_reports_view'), {'export': 'csv', 'status': 'Returned'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8'))))
        self.assertEqual(len(rows), 2)  # header + 1 returned loan
        self.assertEqual(rows[1][12], 'Returned')

    def test_empty_state(self):
        Loan.objects.all().delete()
        self.login_admin()
        response = self.client.get(reverse('loan_reports_view'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['total_loans'], 0)
        self.assertEqual(response.context['loans'], [])


class OverdueReportTests(ReportTestBase):
    def test_only_loans_with_outstanding_units_after_due_date(self):
        self.login_admin()
        response = self.client.get(reverse('overdue_reports'))
        self.assertEqual(response.status_code, 200)

        overdue_ids = [loan.pk for loan in response.context['overdue_loans']]
        # Most overdue first: A (5 days) then B (2 days)
        self.assertEqual(overdue_ids, [self.loan_a.pk, self.loan_b.pk])
        self.assertNotIn(self.loan_c.pk, overdue_ids)  # returned late, nothing outstanding
        self.assertNotIn(self.loan_d.pk, overdue_ids)  # due today is not overdue

    def test_days_overdue_and_outstanding_units(self):
        self.login_admin()
        response = self.client.get(reverse('overdue_reports'))
        loans = {loan.pk: loan for loan in response.context['overdue_loans']}

        self.assertEqual(loans[self.loan_a.pk].days_overdue, 5)
        self.assertEqual(loans[self.loan_b.pk].days_overdue, 2)

        a_codes = sorted(u.asset_code for u in loans[self.loan_a.pk].outstanding_units)
        b_codes = [u.asset_code for u in loans[self.loan_b.pk].outstanding_units]
        self.assertEqual(a_codes, ['T-000', 'T-001'])
        self.assertEqual(b_codes, ['T-003'])  # T-002 was returned

    def test_summary(self):
        self.login_admin()
        summary = self.client.get(reverse('overdue_reports')).context['summary']
        self.assertEqual(summary['total_loans'], 2)
        self.assertEqual(summary['units_outstanding'], 3)
        self.assertEqual(summary['max_days_overdue'], 5)
        self.assertEqual(summary['borrowers'], 1)

    def test_report_changes_when_a_return_is_recorded(self):
        self.login_admin()
        ReturnRecord.objects.create(
            loan=self.loan_b, unit=self.units[3], return_condition='Good')
        summary = self.client.get(reverse('overdue_reports')).context['summary']
        self.assertEqual(summary['total_loans'], 1)  # B is fully returned now

    def test_due_date_filter(self):
        self.login_admin()
        start = (self.today - timedelta(days=3)).isoformat()
        response = self.client.get(reverse('overdue_reports'), {'date_from': start})
        self.assertEqual([l.pk for l in response.context['overdue_loans']], [self.loan_b.pk])

    def test_search_by_asset_code(self):
        self.login_admin()
        response = self.client.get(reverse('overdue_reports'), {'search': 'T-003'})
        self.assertEqual([l.pk for l in response.context['overdue_loans']], [self.loan_b.pk])

    def test_csv_export(self):
        self.login_admin()
        response = self.client.get(reverse('overdue_reports'), {'export': 'csv'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8'))))
        self.assertEqual(len(rows), 3)  # header + 2 overdue loans
        self.assertEqual(rows[1][7], '5')
        self.assertTrue(rows[1][0].startswith('#REQ-'))