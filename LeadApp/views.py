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
from django.db.models.functions import TruncMonth, TruncDate
from decimal import Decimal
from .graph import RevenueDashboard, MonthlySalesTarget, SalesLeaderboard,LeadFunnel,DashboardData
from django.db.models import Q
from django.db import transaction
from django.contrib import messages
from django.urls import reverse
from datetime import datetime
import json
from .models import UserProfile, Lead, LeadFollowUp, LeadStatusHistory, Deal, Commission, DealInstallment, SalesTarget, CallLog, Expense
from django.utils.timezone import now

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


def dashboard(request):
    selected_month = request.GET.get("month")
    dashboard_data = DashboardData(request.user)
    revenue_data = RevenueDashboard(selected_month)
    today = timezone.localdate()   
    total_leads = Lead.objects.count()
    deals_won = Lead.objects.filter(status="won").count()
    total_revenue = (DealInstallment.objects.aggregate(total=Sum("amount")).get("total") or 0)
    followups_today = LeadFollowUp.objects.filter(next_followup_date=today,is_completed=False).count()
    followups_today_list = LeadFollowUp.objects.filter(next_followup_date=today,is_completed=False).select_related("lead", "created_by")[:10]
    leaderboard = (DealInstallment.objects.values("deal__lead__assigned_to__username").annotate(revenue=Sum("amount")).order_by("-revenue")[:5])
    today = timezone.localdate()
    current_year = today.year
    current_month = today.month
    days = []
    daily_revenue = []

    daily_data = (
        DealInstallment.objects
        .filter(
            payment_date__year=current_year,
            payment_date__month=current_month
        )
        .annotate(day=TruncDate("payment_date"))
        .values("day")
        .annotate(total=Sum("amount"))
        .order_by("day")
    )

    for item in daily_data:

        if item["day"]:
            days.append(item["day"].strftime("%d %b"))
            daily_revenue.append(float(item["total"] or 0))

    print(days)    

    for s in leaderboard:
        s["user"] = s["deal__lead__assigned_to__username"]
    lead_funnel = [
        Lead.objects.filter(status="new").count(),
        Lead.objects.filter(status="contacted").count(),
        Lead.objects.filter(status="qualified").count(),
        Lead.objects.filter(status="proposal").count(),
        Lead.objects.filter(status="negotiation").count(),
        Lead.objects.filter(status="won").count(),
    ]
   
    lead_labels = json.dumps([
        "New",
        "Contacted",
        "Qualified",
        "Proposal",
        "Negotiation",
        "Won"
    ])

    lead_values = json.dumps(lead_funnel)

    # -------------------
    # CONTEXT
    # -------------------

    context = {

        # dashboard cards
        "total_leads": total_leads,
        "deals_won": deals_won,
        "revenue": total_revenue,
        "followups_today": followups_today,

        # followups
        "followups_today_list": followups_today_list,
            "leaderboard": leaderboard,
    
        # lead funnel
        "lead_labels": lead_labels,
        "lead_values": lead_values,

        # revenue stats
        "today_revenue": revenue_data["today"],
        "yesterday_revenue": revenue_data["yesterday"],
        "this_month_revenue": revenue_data["this_month"],
        "this_year_revenue": revenue_data["this_year"],

        # daily chart
        "days": revenue_data["days"],
        "daily_revenue": revenue_data["daily"],

        # monthly chart
        "months": revenue_data["months"],
        "monthly_revenue": revenue_data["monthly"],

        # filters
        "selected_month": selected_month,

        # extra dashboard data
        "dashboard_data": dashboard_data,
        "days" : json.dumps(days),
        "daily_revenue" : json.dumps(daily_revenue)
    }
   

    return render(request, "index.html", context)

@login_required
def ViewLead(request):

    user = request.user
    profile = user.profile

    status_filter = request.GET.get("status")
    priority_filter = request.GET.get("priority")

    # Base queryset
    if profile.is_admin or profile.is_lgs:
        base_queryset = Lead.objects.filter(is_deleted=False)

    else:
        base_queryset = Lead.objects.filter(
            Q(is_deleted=False),
            Q(assigned_to=user) | Q(assigned_to__isnull=True)
        ).distinct()

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


@role_required([UserProfile.ROLE_ADMIN, UserProfile.ROLE_LGS, UserProfile.ROLE_SALESMAN])
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

    next_url = request.GET.get("next") or request.POST.get("next")
    user = request.user

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
            lead=lead
        )

        # Only creator or admin can edit
        if not (user.profile.is_admin or followup.created_by == user):
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
            return redirect(next_url + f"#collapse{lead.id}")

        return redirect("ViewLead")

    return render(request, "lead_progress.html", {
        "lead": lead,
        "followup": followup,
        "next_url": next_url
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
    
    if not request.user.profile.is_admin:
        return redirect("dashboard")

    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":

        amount = Decimal(request.POST.get("amount") or 0)
        note = request.POST.get("note")
        payment_date = request.POST.get("payment_date")
    

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

        MonthlyTargetAchieved(request,installment_id,new_amount)
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
def SalesLeaderBoard(request):
    try:
        sales_leaderboard = SalesLeaderboard(request)
        print(sales_leaderboard)

        return render(
            request,
            'SaleLeaderBoard.html',sales_leaderboard
        )

    except Exception as e:
        return HttpResponse(f"Exception: {e}")


@login_required
def add_call_log(request, lead_id):

    lead = get_object_or_404(Lead, id=lead_id)

    call_id = request.GET.get("edit")
    next_url = request.GET.get("next")
    
    if request.method == "POST":

        if call_id:
            
            call = get_object_or_404(CallLog, id=call_id)
            call.call_type = request.POST.get("call_type")
            call.call_status = request.POST.get("call_status")
            call.call_duration = request.POST.get("call_duration")
            call.notes = request.POST.get("notes")
            call.next_followup_date = request.POST.get("next_followup_date")
            call.updated_by = request.user
            call.save()
            
        else:

            CallLog.objects.create(
                lead=lead,
                user=request.user,
                call_type=request.POST.get("call_type"),
                call_status=request.POST.get("call_status"),
                call_duration=request.POST.get("call_duration") or None,
                notes=request.POST.get("notes"),
                next_followup_date=request.POST.get("next_followup_date") or None,
            )

    print('next_url :-', next_url)

    if next_url:
        return redirect(next_url)

    return redirect("ViewLead")



def DashboardIcon(request):

    today = now().date()

    total_leads = Lead.objects.count()

    deals_won = Lead.objects.filter(status="won").count()

    revenue = DealInstallment.objects.aggregate(
        total=Sum("amount")
    )["total"] or 0

    followups_today = LeadFollowUp.objects.filter(
        next_followup_date=today,
        is_completed=False
    ).count()

    followups_today_list = LeadFollowUp.objects.filter(
        next_followup_date=today,
        is_completed=False
    )[:10]

    context = {
        "total_leads": total_leads,
        "deals_won": deals_won,
        "revenue": revenue,
        "followups_today": followups_today,
        "followups_today_list": followups_today_list,
    }

    return render(request, "Dashboard.html", context)






def ViewExpenses(request):
    expenses = Expense.objects.all().order_by("-expense_date")
    return render(request,"view_expenses.html",{"expenses": expenses})



def AddEditExpense(request, id=None):

    expense = None

    if id:
        expense = get_object_or_404(Expense, id=id,is_deleted=False)
        print(expense)

    if request.method == "POST":

        title = request.POST.get("title")
        category = request.POST.get("category")
        amount_input = request.POST.get("amount")
        expense_date = request.POST.get("expense_date")
        lead_source = request.POST.get("lead_source")
       

        try:
            amount = Decimal(amount_input)
        except:
            amount = Decimal("0")

        # UPDATE
        if expense:
            expense.title = title
            expense.category = category
            expense.amount = amount
            expense.expense_date = expense_date
            expense.lead_source = lead_source
            expense.updated_by=request.user
            expense.save()

        # CREATE
        else:
            Expense.objects.create(
                title=title,
                category=category,
                amount=amount,
                expense_date=expense_date,
                lead_source=lead_source,
                created_by=request.user
            )

        return redirect("ViewExpenses")

    return render(request, "AddEditExpenses.html", {
        "expense": expense
    })


def DeleteExpense(request, id):

    expense = get_object_or_404(Expense,id=id)
    expense.soft_delete(request.user) 
    return redirect("ViewExpenses")