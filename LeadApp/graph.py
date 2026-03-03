import json
import calendar
from datetime import timedelta, date

from django.db.models import Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from .models import DealInstallment


def RevenueDashboard(selected_month=None):

    today = timezone.now().date()

    current_year = today.year

    # ✅ FIX MONTH TYPE
    if selected_month:
        try:
            current_month = int(selected_month)
        except:
            current_month = today.month
    else:
        current_month = today.month

    yesterday = today - timedelta(days=1)

    # ======================
    # TODAY / YESTERDAY
    # ======================

    today_total = (
        DealInstallment.objects.filter(
            payment_date=today
        ).aggregate(total=Sum("amount"))["total"] or 0
    )

    yesterday_total = (
        DealInstallment.objects.filter(
            payment_date=yesterday
        ).aggregate(total=Sum("amount"))["total"] or 0
    )

    # ======================
    # THIS MONTH
    # ======================

    this_month_total = (
        DealInstallment.objects.filter(
            payment_date__year=current_year,
            payment_date__month=current_month,
        ).aggregate(total=Sum("amount"))["total"] or 0
    )

    # ======================
    # THIS YEAR
    # ======================

    this_year_total = (
        DealInstallment.objects.filter(
            payment_date__year=current_year,
        ).aggregate(total=Sum("amount"))["total"] or 0
    )

    # ======================
    # DAILY GRAPH
    # ======================

    days_in_month = calendar.monthrange(
        current_year,
        current_month
    )[1]

    days = []
    daily_revenue = []

    for d in range(1, days_in_month + 1):

        dt = date(current_year, current_month, d)

        days.append(dt.strftime("%d %b"))
        daily_revenue.append(0)

    daily_data = (
        DealInstallment.objects
        .filter(
            payment_date__year=current_year,
            payment_date__month=current_month,
        )
        .annotate(day=TruncDate("payment_date"))
        .values("day")
        .annotate(total=Sum("amount"))
    )

    for item in daily_data:

        if item["day"]:

            i = item["day"].day - 1

            if i < len(daily_revenue):

                daily_revenue[i] = float(item["total"] or 0)

    # ======================
    # MONTHLY GRAPH
    # ======================

    months = list(calendar.month_abbr)[1:]
    monthly_revenue = [0] * 12

    monthly_data = (
        DealInstallment.objects
        .filter(
            payment_date__year=current_year,
        )
        .annotate(month=TruncMonth("payment_date"))
        .values("month")
        .annotate(total=Sum("amount"))
    )

    for item in monthly_data:

        if item["month"]:

            i = item["month"].month - 1

            monthly_revenue[i] = float(item["total"] or 0)

    return {

        "today": round(today_total, 0),
        "yesterday": round(yesterday_total, 0),

        "this_month": round(this_month_total, 0),
        "this_year": round(this_year_total, 0),

        "days": json.dumps(days),
        "daily": json.dumps(daily_revenue),

        "months": json.dumps(months),
        "monthly": json.dumps(monthly_revenue),
    }