from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from functools import wraps
from django.db.models import Prefetch
from django.db.models import Count, Sum
from django.db.models import Prefetch
from django.db.models.functions import TruncMonth
from decimal import Decimal
from .graph import RevenueDashboard

from django.db import transaction
from django.contrib import messages
from django.urls import reverse
from datetime import datetime
from .models import UserProfile, Lead, LeadFollowUp, LeadStatusHistory, Deal, Commission, DealInstallment, SalesTarget, CallLog

import json
def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.profile.role not in allowed_roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def index(request):
    return render(request, "login.html")


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            return redirect('dashboard')

        return render(request, 'login.html', {'error': 'Invalid username or password'})

    return render(request, 'login.html')


@login_required
def logout_view(request):
    logout(request)
    return redirect('/')



@login_required
def dashboard(request):

    user = request.user
    today = timezone.now().date()
    
    month = request.GET.get("month")
    rev = RevenueDashboard(month)
    if user.profile.is_admin or user.profile.is_lgs:
        leads = Lead.objects.filter(is_deleted=False)
        followups = LeadFollowUp.objects.filter(lead__is_deleted=False)
        total_users = User.objects.count() if user.profile.is_admin else None

    else:

        leads = Lead.objects.filter(is_deleted=False,assigned_to=user)
        followups = LeadFollowUp.objects.filter(lead__assigned_to=user,lead__is_deleted=False)
        total_users = None

    
    total_leads = leads.count()
    today_leads = leads.filter(date_added__date=today).count()
    converted_leads = leads.filter(status="won").count()
    lost_leads = leads.filter(status="lost").count()
    high_priority_leads = leads.filter(priority="high").exclude(status="won").count()
    overdue_followups = followups.filter(next_followup_date__lt=today,is_completed=False).count()
    today_followups = followups.filter(next_followup_date=today,is_completed=False).count()

    target = SalesTarget.objects.filter(user=request.user,month=today.month,year=today.year).first()


    conversion_rate = 0
    if total_leads > 0:
        conversion_rate = round((converted_leads / total_leads) * 100,2)

    deals = Deal.objects.all()

   
    installments = DealInstallment.objects.filter(is_deleted=False)

    total_revenue = installments.aggregate(total=Sum("amount"))["total"] or 0

    # Paid revenue = actual received money
    paid_revenue = total_revenue

    # Pending revenue = remaining from deals
    pending_revenue = Deal.objects.filter(is_deleted=False).aggregate(total=Sum("deal_value"))["total"] or 0

    pending_revenue  = DealInstallment.objects.filter(is_deleted=False)

    total_revenue = installments.aggregate(total=Sum("amount"))["total"] or 0

    # Paid revenue = actual received money
    paid_revenue = total_revenue

    # Pending revenue = remaining from deals
    pending_revenue = Deal.objects.filter(is_deleted=False).aggregate(total=Sum("deal_value"))["total"] or 0

    pending_revenue = pending_revenue - total_revenue
    months = []
    revenues = []
    monthly_data = (
    DealInstallment.objects
    .filter(is_deleted=False)
    .annotate(month=TruncMonth("payment_date"))
    .values("month")
    .annotate(total=Sum("amount"))
    .order_by("month")
    )

    for item in monthly_data:
        months.append(item["month"].strftime("%b %Y"))
        revenues.append(float(item["total"]))

    total_commission = Commission.objects.aggregate(total=Sum("amount"))["total"] or 0
    salesman_stats = deals.values("lead__assigned_to__username").annotate(total_revenue=Sum("deal_value"),total_deals=Count("id")).order_by("-total_revenue")
    months_list = [
    (1, "Jan"),
    (2, "Feb"),
    (3, "Mar"),
    (4, "Apr"),
    (5, "May"),
    (6, "Jun"),
    (7, "Jul"),
    (8, "Aug"),
    (9, "Sep"),
    (10, "Oct"),
    (11, "Nov"),
    (12, "Dec"),
]

    context = {
        "total_leads": total_leads,
        "today_leads": today_leads,
        "converted_leads": converted_leads,
        "lost_leads": lost_leads,
        "high_priority_leads": high_priority_leads,
        "overdue_followups": overdue_followups,
        "today_followups": today_followups,
        "conversion_rate": conversion_rate,
        "total_users": total_users,
        'total_revenue' : total_revenue,
        "paid_revenue" : paid_revenue,
        "pending_revenue" : pending_revenue,
        "salesman_stats" : salesman_stats,
        "total_commission": total_commission,
        "rev": rev,
        "months_list": months_list,
        "selected_month": int(month) if month else None,
        "target" : target   
        
    }


    return render(request, "index.html", context)

@login_required
def ViewLead(request):

    user = request.user
    profile = user.profile

    status_filter = request.GET.get("status")
    priority_filter = request.GET.get("priority")

    base_queryset = Lead.objects.filter(is_deleted=False)

    # Priority filter
    if priority_filter:
        base_queryset = base_queryset.filter(priority=priority_filter)

    # Status filter
    if status_filter:
        base_queryset = base_queryset.filter(status=status_filter)
    else:
        base_queryset = base_queryset.exclude(status="won")

    # Prefetch followups
    leads = base_queryset.order_by("-date_added").prefetch_related(
    Prefetch(
        "lead_followups",
        queryset=LeadFollowUp.objects.order_by("-created_at")
    )
)

    return render(request, "view_lead.html", {"leads": leads})
@login_required
@role_required([UserProfile.ROLE_ADMIN, UserProfile.ROLE_LGS])
@transaction.atomic
def AddEditLead(request, leadId=None):

    lead = None
    next_url = request.GET.get("next") or request.POST.get("next")
    print("next_ur : ", next_url)

 
    if leadId:
        lead = get_object_or_404(Lead, id=leadId, is_deleted=False)

    sales_users = User.objects.select_related("profile").filter( profile__role=UserProfile.ROLE_SALESMAN)

    if request.method == "POST":

        assigned_ids = request.POST.getlist("userId")

        valid_users = User.objects.filter(id__in=assigned_ids,profile__role=UserProfile.ROLE_SALESMAN)

        form_data = {
            "first_name": request.POST.get("first_name"),
            "last_name": request.POST.get("last_name"),
            "email": request.POST.get("email"),
            "mobile_number": request.POST.get("mobile_number"),
            "company_name": request.POST.get("company_name"),
            "source": request.POST.get("source"),
            "region": request.POST.get("region"),
            "domain_name": request.POST.get("domain_name"),
            "social_accounts": request.POST.get("social_accounts"),
            "budget": request.POST.get("budget") or None,
            "requirements": request.POST.get("requirements"),
            "lead_brief": request.POST.get("lead_brief"),
            "status": request.POST.get("status"),
            "priority": request.POST.get("priority"),
            "verified": request.POST.get("verified"),
            
        }

      
        # UPDATE LEAD
        if lead:

            old_status = lead.status

            for field, value in form_data.items():
                setattr(lead, field, value)

            lead.save()

            # Status history
            if old_status != lead.status:
                LeadStatusHistory.objects.create(
                    lead=lead,
                    old_status=old_status,
                    new_status=lead.status,
                    changed_by=request.user
                )

            messages.success(request, "Lead updated successfully.")

 
        # CREATE LEAD
   
        else:
            lead = Lead.objects.create(**form_data,lead_created_by=request.user )

            messages.success(request, "Lead created successfully.")

        # ManyToMany update
        lead.assigned_to.set(valid_users)

        
        # SAFE REDIRECT LOGIC
        collapse_hash = f"#collapse{lead.id}"
        print("collapse_hash", collapse_hash)
        viewlead_url = reverse("ViewLead")
        

        # Converted → go to converted tab
        if lead.status == "won":
            return redirect( f"{viewlead_url}?status=won{collapse_hash}")

        if next_url and next_url != "None":
            print(f"{next_url}{collapse_hash}")
            return redirect(
                f"{next_url}{collapse_hash}"
            )

        # Default fallback
        return redirect( f"{viewlead_url}{collapse_hash}" )


    return render(request, "createLead.html", {
        "lead": lead,
        "users": sales_users,
        "STATUS_CHOICES": Lead.STATUS_CHOICES,
        "PRIORITY_CHOICES": Lead.PRIORITY_CHOICES,
        "SOURCE_CHOICES": Lead.SOURCE_CHOICES,
        "VERIFIED": Lead.VERIFIED,
        
        "next_url": next_url,
    })

@login_required
def AddEditFollowup(request, lead_id, followup_id=None):

    lead = get_object_or_404(Lead, pk=lead_id, is_deleted=False)
    print(lead)
    next_url = request.GET.get("next") or request.POST.get("next")
    user = request.user
    print(user)

    # Basic lead access check
    if not (
        user.profile.is_admin
        or user.profile.is_lgs
        or user.profile.is_salesman
    ):
        raise PermissionDenied

    followup = None

    if followup_id:
        followup = get_object_or_404(
            LeadFollowUp,
            pk=followup_id,
            lead=lead,
            created_by_id = request.user
        )

        # permission check
        if not (request.user.profile.is_admin or request.user.profile.is_salesman or request.user.profile.is_lgs):
            raise PermissionDenied

    if request.method == "POST":

        note = request.POST.get("note")
        next_date = request.POST.get("next_followup_date")
        is_completed = bool(request.POST.get("is_completed"))

        if followup:
            followup.note = note
            followup.next_followup_date = next_date
            followup.is_completed = is_completed
            followup.save()
        else:
            LeadFollowUp.objects.create(
                lead=lead,
                note=note,
                next_followup_date=next_date,
                is_completed=is_completed,
                created_by=user
            )

        if next_url:
            print('next_url', next_url)
            url = f"#collapse{lead.id}"
            return redirect(next_url + url)


    return render(request, "lead_progress.html", {
        "lead": lead,
        "followup": followup,
        "next_url" :next_url
    })

@login_required
@role_required([UserProfile.ROLE_ADMIN])
def view_user(request):
    users = User.objects.all()
    return render(request, "view_user.html", {'users': users})


@login_required
@role_required([UserProfile.ROLE_ADMIN])
def AddEditUser(request):

    user = None
    profile = None

    user_id = request.GET.get("userId")
    if user_id:
        user = get_object_or_404(User, id=user_id)
        profile = user.profile

    if request.method == "POST":

        role = request.POST.get("role")

        if not user:
            user = User.objects.create_user(
                username=request.POST.get("username"),
                password=request.POST.get("password"),
            )
            profile = UserProfile.objects.create(user=user)

        user.first_name = request.POST.get("first_name")
        user.last_name = request.POST.get("last_name")
        user.email = request.POST.get("email")

        password = request.POST.get("password")
        if password:
            user.set_password(password)

        user.is_staff = True
        user.is_superuser = False
        user.save()

        profile.role = role
        profile.save()

        return redirect("viewusers")

    return render(request, "AddEditUser.html", {
        "edit_user": user,
        "profile": profile
    })

@login_required
def CreateDeal(request, lead_id):

    lead = get_object_or_404(Lead, id=lead_id)
    next_url = request.GET.get("next") or request.POST.get("next")


    if not request.user.profile.is_admin:
        return redirect("dashboard")

    deal = getattr(lead, "deal", None)

    if request.method == "POST":

        deal_value = Decimal(request.POST.get("deal_value") or 0)
        closing_date = request.POST.get("closing_date")
        notes = request.POST.get("notes")

        if deal:
            deal.deal_value = deal_value
            deal.closing_date = closing_date
            deal.notes = notes
        else:
            deal = Deal.objects.create(
                lead=lead,
                deal_value=deal_value,
                closing_date=closing_date,
                notes=notes,
                created_by=request.user
            )

        deal.update_payment_status()

        if next_url:
            url = f"#collapse{deal.lead.id}"
            return redirect(next_url + url)

    return render(request, "CreateDeal.html", {
        "lead": lead,
        "deal": deal
    })
@login_required
def UpdateDeal(request, deal_id):

    deal = get_object_or_404(Deal, id=deal_id)
    next_url = request.GET.get("next") or request.POST.get("next")


    if not request.user.profile.is_admin:
        return redirect("dashboard")

    if request.method == "POST":

        deal_value = Decimal(request.POST.get("deal_value") or deal.deal_value)

        deal.deal_value = deal_value
        deal.update_payment_status()
        if next_url:
            url = f"#collapse{deal.lead.id}"
            return redirect(next_url + url)
      

    return render(request, "CreateDeal.html", {
        "deal": deal
    })

@login_required
def AddInstallment(request, deal_id):

    deal = get_object_or_404(Deal, id=deal_id)
    print('deal :', deal)

    if not request.user.profile.is_admin:
        return redirect("dashboard")

    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":

        amount = Decimal(request.POST.get("amount") or 0)
        note = request.POST.get("note")
        payment_date = request.POST.get("payment_date")
        print("amount : ", amount)
        print("note : ", note)
        print("payment_date : ", payment_date)


        DealInstallment.objects.create(
            deal=deal,
            amount=amount,
            note=note,
            payment_date=payment_date,
            created_by=request.user
        )

        deal.update_payment_status()

        if next_url:
            url = f"#collapse{deal.lead.id}"
            return redirect(next_url + url)

        return redirect("ViewLead")

    return render(request, "InstallmentPlan.html", {
        "deal": deal,
        "next": next_url
    })


@login_required
def DeleteInstallment(request, installment_id):

    installment = get_object_or_404(DealInstallment, id=installment_id)

    if not request.user.profile.is_admin:
        return redirect("dashboard")

    deal = installment.deal

    # Soft delete related commissions
    commissions = installment.commissions.filter(is_deleted=False)

    for commission in commissions:
        commission.soft_delete()

    # Soft delete installment
    installment.soft_delete()

    # Update deal payment status
    deal.update_payment_status()

    return redirect("ViewLead")


@transaction.atomic
def EditInstallment(request, installment_id):

    installment = get_object_or_404(
        DealInstallment,
        id=installment_id,
        is_deleted=False
    )

    if not request.user.profile.is_admin:
        return redirect("dashboard")

    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":

        new_amount = Decimal(request.POST.get("amount") or 0)

        # 🔒 Prevent editing if commission already paid
        if installment.commissions.filter(is_paid=True).exists():
            return redirect("ViewLead")

        installment.amount = new_amount
        installment.note = request.POST.get("note")
        installment.payment_date = request.POST.get("payment_date")
        installment.save()

        # 🔥 Recalculate commissions safely
        for commission in installment.commissions.filter(is_deleted=False):
            commission.amount = ( new_amount * commission.percentage) / Decimal("100")
            commission.save()

        # Update deal payment status
        installment.deal.update_payment_status()

        if next_url:
            url = f"#collapse{installment.deal.lead.id}"
            return redirect(next_url + url)

        return redirect("ViewLead")

    return render(request, "InstallmentPlan.html", {
        "installment": installment,
        "deal": installment.deal,
        "next": next_url
    })


@login_required
def CommissionLedger(request):

    user_id = request.GET.get("user")
    month = request.GET.get("month")

    commissions = Commission.objects.select_related(
        "user",
        "installment",
        "installment__deal"
    )

    # Filter by user
    if user_id:
        commissions = commissions.filter(user_id=user_id)

    # Filter by month
    if month:
        commissions = commissions.filter(
            installment__payment_date__month=int(month),
            installment__payment_date__year=timezone.now().year
        )

    commissions = commissions.order_by("-installment__payment_date")

    total_commission = commissions.aggregate(
        total=Sum("amount")
    )["total"] or 0

    total_paid = commissions.filter(is_paid=True).aggregate(
        total=Sum("amount")
    )["total"] or 0

    total_unpaid = total_commission - total_paid

    return render(
        request,
        "commission_ledger.html",
        {
            "commissions": commissions,
            "total_commission": total_commission,
            "total_paid": total_paid,
            "total_unpaid": total_unpaid,
        }
    )


@login_required
def mark_commission_paid(request, pk):

    commission = get_object_or_404(Commission, pk=pk)

    commission.is_paid = True
    commission.paid_at = timezone.now()
    commission.save()

    return redirect("commission-ledger")

@login_required
def commission_rollback(request, pk):

    commission = get_object_or_404(Commission, pk=pk)

    commission.is_paid = False
    commission.paid_at = timezone.now()
    commission.save()

    return redirect("commission-ledger")

@login_required
def AddSalesTarget(request, userId):

    users = User.objects.filter(profile__role="SALESMAN")
    

    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":

        month = request.POST.get("month")
        year = request.POST.get("year")
        target_amount = request.POST.get("target_amount")

        SalesTarget.objects.create(
            user_id=userId,
            month=month,
            year=year,
            target_amount=target_amount
        )

        messages.success(request, "Sales Target Saved")

        if next_url:
            return redirect(next_url)

        return redirect("dashboard")

    return render(request, "AddSalesTarget.html", {
        "users": users,
        "selected_user": userId,
        "current_year": datetime.now().year,
        "next_url": next_url
    })


@login_required
def add_call_log(request, lead_id):

    lead = get_object_or_404(Lead, id=lead_id)

    if request.method == "POST":

        CallLog.objects.create(
            lead=lead,
            user=request.user,
            call_type=request.POST.get("call_type"),
            call_status=request.POST.get("call_status"),
            call_duration=request.POST.get("call_duration") or None,
            notes=request.POST.get("notes"),
            next_followup_date=request.POST.get("next_followup_date") or None,
        )

    next_url = request.GET.get("next")

    if next_url:
        return redirect(next_url)

    return redirect("ViewLead")