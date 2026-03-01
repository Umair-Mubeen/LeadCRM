from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
import calendar
from .models import Deal

def RevenueGraph():

    current_year = timezone.now().year
    last_year = current_year - 1

    this_year_data = (
        Deal.objects
        .filter(closing_date__year=current_year, payment_status="paid")
        .annotate(month=TruncMonth("closing_date"))
        .values("month")
        .annotate(total=Sum("deal_value"))
        .order_by("month")
    )

    last_year_data = (
        Deal.objects
        .filter(closing_date__year=last_year, payment_status="paid")
        .annotate(month=TruncMonth("closing_date"))
        .values("month")
        .annotate(total=Sum("deal_value"))
        .order_by("month")
    )

    months = list(calendar.month_abbr)[1:]

    this_year_revenue = [0] * 12
    last_year_revenue = [0] * 12

    for item in this_year_data:
        index = item["month"].month - 1
        this_year_revenue[index] = float(item["total"] or 0)

    for item in last_year_data:
        index = item["month"].month - 1
        last_year_revenue[index] = float(item["total"] or 0)

    total_this_year = sum(this_year_revenue)
    total_last_year = sum(last_year_revenue)

    growth = 0
    if total_last_year > 0:
        growth = ((total_this_year - total_last_year) / total_last_year) * 100

    avg_monthly = total_this_year / 12
    best_month_value = max(this_year_revenue)
    best_month = months[this_year_revenue.index(best_month_value)]

    return {
        "months": months,
        "this_year": this_year_revenue,
        "last_year": last_year_revenue,
        "total_revenue": round(total_this_year, 2),
        "growth": round(growth, 1),
        "avg_monthly": round(avg_monthly, 2),
        "best_month": best_month,
    }