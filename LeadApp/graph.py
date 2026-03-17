import json
import calendar
from datetime import timedelta, date
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from .models import (
    Deal,
    Lead,
    Commission,
    SalesTarget,
    DealInstallment
)


import json
import calendar
from datetime import timedelta, date

from django.db.models import Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from .models import DealInstallment


def RevenueDashboard(selected_month=None):

    today = timezone.localdate()
    current_year = today.year

    try:
        current_month = int(selected_month) if selected_month else today.month
    except ValueError:
        current_month = today.month

    yesterday = today - timedelta(days=1)


    today_total = (
        DealInstallment.objects
        .filter(payment_date=today)
        .aggregate(total=Sum("amount"))
        .get("total") or 0
    )

    yesterday_total = (
        DealInstallment.objects
        .filter(payment_date=yesterday)
        .aggregate(total=Sum("amount"))
        .get("total") or 0
    )

    this_month_total = (
        DealInstallment.objects
        .filter(
            payment_date__year=current_year,
            payment_date__month=current_month
        )
        .aggregate(total=Sum("amount"))
        .get("total") or 0
    )

    this_year_total = (
        DealInstallment.objects
        .filter(payment_date__year=current_year)
        .aggregate(total=Sum("amount"))
        .get("total") or 0
    )


    days_in_month = calendar.monthrange(current_year, current_month)[1]

    days = []
    daily_revenue = [0] * days_in_month

    for d in range(1, days_in_month + 1):
        dt = date(current_year, current_month, d)
        days.append(dt.strftime("%d %b"))

    daily_data = (
        DealInstallment.objects
        .filter(
            payment_date__year=current_year,
            payment_date__month=current_month
        )
        .annotate(day=TruncDate("payment_date"))
        .values("day")
        .annotate(total=Sum("amount"))
    )

    for item in daily_data:
        if item["day"]:
            index = item["day"].day - 1
            daily_revenue[index] = float(item["total"] or 0)

    # ======================
    # MONTHLY GRAPH DATA
    # ======================

    months = list(calendar.month_abbr)[1:]
    monthly_revenue = [0] * 12

    monthly_data = (
        DealInstallment.objects
        .filter(payment_date__year=current_year)
        .annotate(month=TruncMonth("payment_date"))
        .values("month")
        .annotate(total=Sum("amount"))
    )

    for item in monthly_data:
        if item["month"]:
            index = item["month"].month - 1
            monthly_revenue[index] = float(item["total"] or 0)

    # ------------------
    # Return Data
    # ------------------

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



def MonthlySalesTarget(user):

    today = timezone.localdate()

    target = SalesTarget.objects.filter(
        user=user,
        month=today.month,
        year=today.year
    ).first()

    monthly_target = target.target_amount if target else 0

    achieved_sales = (
        Deal.objects
        .filter(
            created_by=user,
            payment_status="paid",
            created_at__year=today.year,
            created_at__month=today.month
        )
        .aggregate(total=Sum("deal_value"))["total"] or 0
    )

    remaining_target = max(monthly_target - achieved_sales, 0)

    target_progress = 0

    if monthly_target > 0:
        target_progress = round(
            (achieved_sales / monthly_target) * 100
        )

    return {

        "monthly_target": monthly_target,
        "achieved_sales": achieved_sales,
        "remaining_target": remaining_target,
        "target_progress": target_progress,
    }




def SalesLeaderboard():

    today = timezone.localdate()

    leaderboard = (
        Deal.objects
        .filter(
            payment_status="paid",
            created_at__year=today.year,
            created_at__month=today.month,
            is_deleted=False
        )
        .values(
            "lead__assigned_to",
            "lead__assigned_to__username"
        )
        .annotate(total_sales=Sum("deal_value"))
        .order_by("-total_sales")
    )

    data = []

    for row in leaderboard:

        user_id = row["lead__assigned_to"]

        commission = (
            Commission.objects
            .filter(
                user_id=user_id,
                created_at__year=today.year,
                created_at__month=today.month
            )
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        target = SalesTarget.objects.filter(
            user_id=user_id,
            month=today.month,
            year=today.year
        ).first()

        target_amount = target.target_amount if target else 0

        progress = 0

        if target_amount > 0:
            progress = round(
                (row["total_sales"] / target_amount) * 100
            )

        row["commission"] = commission
        row["target"] = target_amount
        row["progress"] = progress

        data.append(row)

    return {"sales_leaderboard": data}




def LeadFunnel():

    return {

        "lead_funnel": [

            Lead.objects.filter(status="new").count(),

            Lead.objects.filter(status="contacted").count(),

            Lead.objects.filter(status="qualified").count(),

            Lead.objects.filter(status="proposal").count(),

            Lead.objects.filter(status="negotiation").count(),

            Lead.objects.filter(status="won").count(),

        ]
    }




def DashboardData(user):

    context = {}

    context.update(RevenueDashboard())
    context.update(MonthlySalesTarget(user))
    context.update(SalesLeaderboard())
    context.update(LeadFunnel())

    return context
