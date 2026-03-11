import json
import calendar
from datetime import timedelta, date
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from .models import Deal, SalesTarget, DealInstallment
from django.shortcuts import render, redirect, get_object_or_404


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


def MonthlySalesTarget(request):
    today = timezone.localdate()  # safer than timezone.now()

    target = SalesTarget.objects.filter(
        user=request.user,
        month=today.month,
        year=today.year
    ).first()

    monthly_target = target.target_amount if target else 0

    achieved_sales = Deal.objects.filter(
        created_by=request.user,
        payment_status="paid",
        created_at__year=today.year,
        created_at__month=today.month
    ).aggregate(total=Sum("deal_value"))["total"] or 0

    remaining_target = max(monthly_target - achieved_sales, 0)

    target_progress = 0
    if monthly_target > 0:
        target_progress = round((achieved_sales / monthly_target) * 100)

    return {
        "monthly_target": monthly_target,
        "achieved_sales": achieved_sales,
        "remaining_target": remaining_target,
        "target_progress": target_progress,
    }


from django.utils import timezone
from django.db.models import Sum
from .models import Deal, Commission, SalesTarget


def SalesLeaderboard(request):

    today = timezone.localdate()

    leaderboard = (
        Deal.objects.filter(
            payment_status="paid",
            created_at__year=today.year,
            created_at__month=today.month,
            is_deleted=False
        )
        .values(
            "lead__assigned_to__id",
            "lead__assigned_to__username"
        )
        .annotate(
            total_sales=Sum("deal_value")
        )
        .order_by("-total_sales")
    )

    # enrich leaderboard rows
    data = []

    for row in leaderboard:

        user_id = row["lead__assigned_to__id"]

        commission = Commission.objects.filter(
            user_id=user_id,
            created_at__year=today.year,
            created_at__month=today.month
        ).aggregate(total=Sum("amount"))["total"] or 0

        target = SalesTarget.objects.filter(
            user_id=user_id,
            month=today.month,
            year=today.year
        ).first()

        target_amount = target.target_amount if target else 0

        progress = 0
        if target_amount > 0:
            progress = round((row["total_sales"] / target_amount) * 100)

        row["commission"] = commission
        row["target"] = target_amount
        row["progress"] = progress

        data.append(row)

    return {"sales_leaderboard": data}



def MonthlyTargetAchieved(request,installment_id,new_amount):
        
    today = timezone.localdate()

    installment = get_object_or_404(
            DealInstallment,
            id=installment_id,
            is_deleted=False
        )

    salesman = installment.deal.lead.assigned_to


    # 🔎 Get monthly target
    target = SalesTarget.objects.filter(
        user=salesman,
        month=today.month,
        year=today.year
    ).first()

    target_amount = target.target_amount if target else 0


    # 🔎 Calculate monthly sales
    monthly_sales = Deal.objects.filter(
        lead__assigned_to=salesman,
        payment_status="paid",
        created_at__year=today.year,
        created_at__month=today.month,
        is_deleted=False
    ).aggregate(total=Sum("deal_value"))["total"] or 0


    # 🔒 Prevent editing if commission already paid
    if installment.commissions.filter(is_paid=True).exists():
        return redirect("ViewLead")


    installment.amount = new_amount
    installment.note = request.POST.get("note")
    installment.payment_date = request.POST.get("payment_date")
    installment.save()


    # 🎯 Only calculate commission if target achieved
    if monthly_sales >= target_amount:

        for commission in installment.commissions.filter(is_deleted=False):

            commission.amount = (
                new_amount * commission.percentage
            ) / Decimal("100")

            commission.save()


    # Update deal payment status
    installment.deal.update_payment_status()