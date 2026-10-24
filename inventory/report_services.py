"""
Reusable business logic for the Loan Report and Overdue Report (Part 2: A5, A7).

Everything here is derived from stored transactions (Loan, UnitAllocation,
ReturnRecord) through the ORM. Nothing is hard-coded, so the reports change
whenever the database changes.

Definitions used by the reports
-------------------------------
units_issued    : non-cancelled UnitAllocation rows of the loan's request
units_returned  : distinct units that have a ReturnRecord for the loan
outstanding     : units_issued - units_returned (never below 0)
status          : Issued            -> nothing returned yet
                  Partially Returned-> some, but not all, units returned
                  Returned          -> every issued unit returned
overdue         : outstanding > 0 AND today > due_date
days_overdue    : 0 on/before due date, otherwise (today - due_date).days
                  (always 0 for loans with nothing outstanding)
"""
import csv
from collections import defaultdict
from datetime import datetime

from django.db.models import Count, F, Q
from django.http import HttpResponse
from django.utils import timezone

from .models import Loan, ReturnRecord, UnitAllocation

LOAN_STATUSES = ('Issued', 'Partially Returned', 'Returned')
PAGE_SIZE = 10


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def parse_date(value):
    """Return a date from a 'YYYY-MM-DD' string, or None if empty/invalid."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def today_date():
    return timezone.localdate()


def overdue_days(due_date, today):
    """Calendar-day difference; zero before or on the due date (Part 5)."""
    return max((today - due_date).days, 0)


def loan_status(units_issued, units_returned):
    if units_issued > 0 and units_returned >= units_issued:
        return 'Returned'
    if units_returned > 0:
        return 'Partially Returned'
    return 'Issued'


def csv_safe(value):
    """Neutralise spreadsheet formula injection in exported cells."""
    text = '' if value is None else str(value)
    if text[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + text
    return text


def csv_response(filename, header, rows):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow([csv_safe(cell) for cell in row])
    return response


# --------------------------------------------------------------------------
# Querysets
# --------------------------------------------------------------------------
def _search_ids(search):
    """
    Loan ids that match the search text (borrower, item name, asset code).
    Done as a sub-query so the search joins can never inflate the
    units_issued / units_returned counts that are annotated afterwards.
    """
    q = (
        Q(borrow_request__owner__username__icontains=search)
        | Q(borrow_request__owner__first_name__icontains=search)
        | Q(borrow_request__owner__last_name__icontains=search)
        | Q(borrow_request__requestitem__catalog_item__name__icontains=search)
        | Q(borrow_request__requestitem__unitallocation__unit__asset_code__icontains=search)
    )
    return Loan.objects.filter(q).values('pk')


def _annotate(loans):
    return loans.annotate(
        units_issued=Count(
            'borrow_request__requestitem__unitallocation',
            filter=Q(borrow_request__requestitem__unitallocation__is_cancelled=False),
            distinct=True,
        ),
        units_returned=Count('returnrecord__unit', distinct=True),
    )


def _finish(loans):
    return loans.select_related(
        'borrow_request__owner', 'issue_actor'
    ).prefetch_related(
        'borrow_request__requestitem_set__catalog_item'
    )


def loan_report_queryset(search='', date_from=None, date_to=None, status=''):
    """Issued loans filtered by issue date, status and search text."""
    loans = Loan.objects.all()
    if search:
        loans = loans.filter(pk__in=_search_ids(search))
    if date_from:
        loans = loans.filter(issue_date__date__gte=date_from)
    if date_to:
        loans = loans.filter(issue_date__date__lte=date_to)

    loans = _annotate(loans)

    if status == 'Returned':
        loans = loans.filter(units_issued__gt=0, units_returned__gte=F('units_issued'))
    elif status == 'Partially Returned':
        loans = loans.filter(units_returned__gt=0, units_returned__lt=F('units_issued'))
    elif status == 'Issued':
        loans = loans.filter(units_returned=0)

    return _finish(loans).order_by('-issue_date', '-pk')


def overdue_report_queryset(today, search='', date_from=None, date_to=None):
    """Loans with units still outstanding after the due date (filtered by due date)."""
    loans = Loan.objects.filter(due_date__lt=today)
    if search:
        loans = loans.filter(pk__in=_search_ids(search))
    if date_from:
        loans = loans.filter(due_date__gte=date_from)
    if date_to:
        loans = loans.filter(due_date__lte=date_to)

    loans = _annotate(loans).filter(units_returned__lt=F('units_issued'))
    return _finish(loans).order_by('due_date', 'pk')


# --------------------------------------------------------------------------
# Decorating loans with the attributes the templates expect
# --------------------------------------------------------------------------
def decorate_loans(loans, today):
    """
    Accepts an iterable of annotated Loan objects and attaches the attributes
    used by the report templates:

        loan.request            -> the BorrowRequest
        loan.issued_by          -> the releasing admin
        loan.status             -> Issued / Partially Returned / Returned
        loan.units_outstanding  -> units not yet returned
        loan.issued_units       -> every unit issued on the loan
        loan.outstanding_units  -> units not yet returned (objects)
        loan.days_overdue       -> 0 unless outstanding units after due date
        loan.is_overdue         -> bool

    Uses two extra queries for the whole list, not two per loan.
    """
    loans = list(loans)
    if not loans:
        return loans

    request_ids = [loan.borrow_request_id for loan in loans]
    loan_ids = [loan.pk for loan in loans]

    units_by_request = defaultdict(dict)
    allocations = (
        UnitAllocation.objects
        .filter(request_item__borrow_request_id__in=request_ids, is_cancelled=False)
        .select_related('unit__catalog_item', 'request_item')
        .order_by('unit__asset_code')
    )
    for alloc in allocations:
        units_by_request[alloc.request_item.borrow_request_id][alloc.unit_id] = alloc.unit

    returned_by_loan = defaultdict(set)
    for loan_id, unit_id in ReturnRecord.objects.filter(
            loan_id__in=loan_ids).values_list('loan_id', 'unit_id'):
        returned_by_loan[loan_id].add(unit_id)

    for loan in loans:
        issued = units_by_request[loan.borrow_request_id]
        returned_ids = returned_by_loan[loan.pk]

        loan.request = loan.borrow_request
        loan.issued_by = loan.issue_actor
        loan.status = loan_status(loan.units_issued, loan.units_returned)
        loan.units_outstanding = max(loan.units_issued - loan.units_returned, 0)
        loan.issued_units = list(issued.values())
        loan.outstanding_units = [u for uid, u in issued.items() if uid not in returned_ids]
        loan.days_overdue = (
            overdue_days(loan.due_date, today) if loan.units_outstanding > 0 else 0
        )
        loan.is_overdue = loan.days_overdue > 0
    return loans


# --------------------------------------------------------------------------
# Summary cards
# --------------------------------------------------------------------------
def loan_summary(loans):
    """Totals over ALL filtered loans (not just the current page)."""
    total = issued = returned = 0
    for units_issued, units_returned in loans.values_list('units_issued', 'units_returned'):
        total += 1
        issued += units_issued
        returned += units_returned
    return {
        'total_loans': total,
        'units_issued': issued,
        'units_returned': returned,
        'units_outstanding': max(issued - returned, 0),
    }


def overdue_summary(loans, today):
    total = outstanding = max_days = 0
    borrowers = set()
    rows = loans.values_list('units_issued', 'units_returned', 'due_date', 'borrow_request__owner_id')
    for units_issued, units_returned, due_date, owner_id in rows:
        total += 1
        outstanding += max(units_issued - units_returned, 0)
        max_days = max(max_days, overdue_days(due_date, today))
        borrowers.add(owner_id)
    return {
        'total_loans': total,
        'units_outstanding': outstanding,
        'max_days_overdue': max_days,
        'borrowers': len(borrowers),
    }


# --------------------------------------------------------------------------
# CSV exports
# --------------------------------------------------------------------------
def _borrower_name(owner):
    return f'{owner.first_name} {owner.last_name}'.strip() or owner.username


def _items_text(loan):
    return '; '.join(
        f'{ri.quantity}x {ri.catalog_item.name}'
        for ri in loan.request.requestitem_set.all()
    )


def _codes_text(units):
    return '; '.join(u.asset_code for u in units)


def loan_report_csv(loans, today):
    rows = []
    for loan in decorate_loans(loans, today):
        owner = loan.request.owner
        rows.append([
            f'#REQ-{loan.borrow_request_id}',
            f'LOAN-{loan.pk}',
            _borrower_name(owner),
            owner.username,
            _items_text(loan),
            _codes_text(loan.issued_units),
            timezone.localtime(loan.issue_date).strftime('%Y-%m-%d %H:%M'),
            loan.issued_by.username if loan.issued_by else '',
            loan.due_date.strftime('%Y-%m-%d'),
            loan.units_issued,
            loan.units_returned,
            loan.units_outstanding,
            loan.status,
            'Yes' if loan.is_overdue else 'No',
            loan.days_overdue,
        ])
    header = [
        'Request ID', 'Loan ID', 'Borrower', 'Username', 'Items', 'Asset Codes',
        'Issued On', 'Issued By', 'Due Date', 'Units Issued', 'Units Returned',
        'Units Outstanding', 'Status', 'Overdue', 'Days Overdue',
    ]
    return csv_response(f'loan_report_{today:%Y%m%d}.csv', header, rows)


def _severity(days):
    if days >= 8:
        return '8+ days'
    if days >= 4:
        return '4-7 days'
    return '1-3 days'


def overdue_report_csv(loans, today):
    rows = []
    for loan in decorate_loans(loans, today):
        owner = loan.request.owner
        rows.append([
            f'#REQ-{loan.borrow_request_id}',
            f'LOAN-{loan.pk}',
            _borrower_name(owner),
            owner.username,
            '; '.join(f'{u.catalog_item.name} ({u.asset_code})' for u in loan.outstanding_units),
            loan.due_date.strftime('%Y-%m-%d'),
            loan.units_outstanding,
            loan.days_overdue,
            _severity(loan.days_overdue),
        ])
    header = [
        'Request ID', 'Loan ID', 'Borrower', 'Username', 'Outstanding Units',
        'Due Date', 'Units Outstanding', 'Days Overdue', 'Severity',
    ]
    return csv_response(f'overdue_report_{today:%Y%m%d}.csv', header, rows)