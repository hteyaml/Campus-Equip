# --- Loan & Overdue Reports backend ---

"""
Admin-only Loan Report and Overdue Report views (Part 2: A5, A7).

Both pages are read-only (GET). Every view is protected by @admin_required,
which also rejects deactivated accounts. The CSV export uses the same filters
as the page, via ?export=csv.
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render

from .decorators import admin_required
from .report_services import (
    LOAN_STATUSES,
    PAGE_SIZE,
    decorate_loans,
    loan_report_csv,
    loan_report_queryset,
    loan_summary,
    overdue_report_csv,
    overdue_report_queryset,
    overdue_summary,
    parse_date,
    today_date,
)


def _read_filters(request):
    """Read and validate the GET filters shared by both reports."""
    search = request.GET.get('search', '').strip()[:100]
    raw_from = request.GET.get('date_from', '').strip()
    raw_to = request.GET.get('date_to', '').strip()
    date_from = parse_date(raw_from)
    date_to = parse_date(raw_to)

    if raw_from and date_from is None:
        messages.warning(request, 'The "from" date is invalid and was ignored.')
    if raw_to and date_to is None:
        messages.warning(request, 'The "to" date is invalid and was ignored.')
    if date_from and date_to and date_from > date_to:
        messages.warning(request, 'The "from" date is later than the "to" date, so no records can match.')

    return search, date_from, date_to


@admin_required
def loan_reports_view(request):
    today = today_date()
    search, date_from, date_to = _read_filters(request)

    status = request.GET.get('status', '').strip()
    if status not in LOAN_STATUSES:
        status = ''

    loans_qs = loan_report_queryset(search, date_from, date_to, status)

    if request.GET.get('export') == 'csv':
        return loan_report_csv(loans_qs, today)

    page_obj = Paginator(loans_qs, PAGE_SIZE).get_page(request.GET.get('page'))
    context = {
        'summary': loan_summary(loans_qs),
        'loans': decorate_loans(page_obj.object_list, today),
        'page_obj': page_obj,
        'today': today,
    }
    return render(request, 'admin/loan_reports_view.html', context)


@admin_required
def overdue_reports_view(request):
    today = today_date()
    search, date_from, date_to = _read_filters(request)

    overdue_qs = overdue_report_queryset(today, search, date_from, date_to)

    if request.GET.get('export') == 'csv':
        return overdue_report_csv(overdue_qs, today)

    page_obj = Paginator(overdue_qs, PAGE_SIZE).get_page(request.GET.get('page'))
    context = {
        'summary': overdue_summary(overdue_qs, today),
        'overdue_loans': decorate_loans(page_obj.object_list, today),
        'page_obj': page_obj,
        'today': today,
    }
    return render(request, 'admin/overdue_reports_view.html', context)