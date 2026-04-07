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
from .graph import RevenueDashboard, MonthlySalesTarget, Sales_Leader_board,LeadFunnel,DashboardData
from django.db.models import Q
from django.db import transaction
from django.contrib import messages
from django.urls import reverse
from datetime import datetime
import json
from .models import UserProfile, Lead, LeadFollowUp, LeadStatusHistory, Deal, Commission, DealInstallment, SalesTarget, CallLog, Expense
from django.utils.timezone import now
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from calendar import month_name

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
    try:
        # =========================
        # DATE
        # =========================
        today = timezone.localdate()
        current_year = today.year
        current_month = today.month

        # =========================
        # BASIC STATS
        # =========================
        total_leads = Lead.objects.count()
        deals_won = Lead.objects.filter(status="won").count()

        # followups_qs = LeadFollowUp.objects.filter(
        #     next_followup_date=today,
        #     is_completed=False
        # ).select_related("lead", "created_by")

        followups_qs = LeadFollowUp.objects.filter(is_completed=False).select_related("lead", "created_by").order_by("next_followup_date")

        followups_today = followups_qs.count()
        followups_today_list = followups_qs[:10]

        # =========================
        # FINANCIALS (SINGLE SOURCE)
        # =========================
        total_revenue = DealInstallment.objects.aggregate(
            total=Sum("amount")
        )["total"] or 0

        total_expenses = Expense.objects.aggregate(
            total=Sum("amount")
        )["total"] or 0

        total_commission = Commission.objects.aggregate(
            total=Sum("amount")
        )["total"] or 0

        net_profit = total_revenue - total_expenses - total_commission

        # =========================
        # USER DISTRIBUTION
        # =========================
        roles = ["ADMIN", "LGS", "SALESMAN"]

        user_counts = UserProfile.objects.filter(
            role__in=roles
        ).values("role").annotate(count=Count("id"))

        user_dict = {i["role"]: i["count"] for i in user_counts}

        user_labels = json.dumps(["Admin", "LGS", "Sales Man"])
        user_values = json.dumps([user_dict.get(r, 0) for r in roles])

        # =========================
        # LEAD FUNNEL
        # =========================
        lead_values = json.dumps([
            Lead.objects.filter(status="new").count(),
            Lead.objects.filter(status="contacted").count(),
            Lead.objects.filter(status="qualified").count(),
            Lead.objects.filter(status="proposal").count(),
            Lead.objects.filter(status="negotiation").count(),
            Lead.objects.filter(status="won").count(),
        ])

        # =========================
        # LEADERBOARD
        # =========================
        leaderboard = list(
            DealInstallment.objects.values(
                "deal__lead__assigned_to__username"
            )
            .annotate(revenue=Sum("amount"))
            .order_by("-revenue")[:5]
        )

        for s in leaderboard:
            s["user"] = s.pop("deal__lead__assigned_to__username", "N/A")

        # =========================
        # MONTHLY PROFIT (FIXED)
        # =========================
        def norm(m):
            return m.date() if hasattr(m, "date") else m

        profit_data = {}

        # Revenue
        for r in Deal.objects.filter(payment_status='paid') \
                .annotate(month=TruncMonth('payment_date')) \
                .values('month').annotate(total=Sum('deal_value')):

            if r['month']:
                m = norm(r['month'])
                profit_data[m] = {
                    'revenue': r['total'] or 0,
                    'expense': 0,
                    'commission': 0
                }

        # Expense
        for e in Expense.objects.annotate(month=TruncMonth('expense_date')) \
                .values('month').annotate(total=Sum('amount')):

            if e['month']:
                m = norm(e['month'])
                profit_data.setdefault(m, {
                    'revenue': 0,
                    'expense': 0,
                    'commission': 0
                })
                profit_data[m]['expense'] = e['total'] or 0

        # Commission
        for c in Commission.objects.annotate(month=TruncMonth('created_at')) \
                .values('month').annotate(total=Sum('amount')):

            if c['month']:
                m = norm(c['month'])
                profit_data.setdefault(m, {
                    'revenue': 0,
                    'expense': 0,
                    'commission': 0
                })
                profit_data[m]['commission'] = c['total'] or 0

        # Final lists
        months = []
        monthly_revenue = []
        monthly_expense = []
        monthly_profit = []

        for m in sorted(profit_data.keys()):
            d = profit_data[m]
            p = d['revenue'] - d['expense'] - d['commission']

            months.append(m.strftime('%b'))
            monthly_revenue.append(float(d['revenue']))
            monthly_expense.append(float(d['expense']))
            monthly_profit.append(float(p))

        # =========================
        # DAILY REVENUE
        # =========================
        days = []
        daily_revenue = []

        daily_qs = Deal.objects.filter(
            payment_status='paid',
            payment_date__year=current_year,
            payment_date__month=current_month
        ).annotate(
            day=TruncDate('payment_date')
        ).values('day').annotate(
            total=Sum('deal_value')
        ).order_by('day')

        for item in daily_qs:
            if item["day"]:
                days.append(item["day"].strftime("%d %b"))
                daily_revenue.append(float(item["total"] or 0))

        # =========================
        # SALES TARGET VS ACHIEVED
        # =========================
        targets = SalesTarget.objects.filter(
            month=current_month
        ).values('user__username').annotate(
            target=Sum('target_amount')
        )

        achieved = Deal.objects.filter(
            payment_status='paid',
            payment_date__month=current_month,
            payment_date__year=current_year
        ).values('created_by__username').annotate(
            achieved=Sum('deal_value')
        )

        data = {}

        for t in targets:
            user = t['user__username']
            data[user] = {
                'target': float(t['target'] or 0),
                'achieved': 0
            }

        for a in achieved:
            user = a['created_by__username']
            data.setdefault(user, {'target': 0, 'achieved': 0})
            data[user]['achieved'] = float(a['achieved'] or 0)

        sales_users = []
        sales_target = []
        sales_achieved = []

        for user, val in data.items():
            sales_users.append(user)
            sales_target.append(val['target'])
            sales_achieved.append(val['achieved'])

        # =========================
        # FINAL CONTEXT
        # =========================
        context = {
            # cards
            "total_leads": total_leads,
            "deals_won": deals_won,
            "revenue": total_revenue,
            "expense": total_expenses,
            "commission": total_commission,
            "net_profit": net_profit,

            # followups
            "followups_today": followups_today,
            "followups_today_list": followups_today_list,

            # charts
            "leaderboard": leaderboard,
            "lead_values": lead_values,
            "user_labels": user_labels,
            "user_values": user_values,

            "months": json.dumps(months),
            "monthly_revenue": json.dumps(monthly_revenue),
            "monthly_expense": json.dumps(monthly_expense),
            "monthly_profit": json.dumps(monthly_profit),

            "days": json.dumps(days),
            "daily_revenue": json.dumps(daily_revenue),

            "sales_users": json.dumps(sales_users),
            "sales_target": json.dumps(sales_target),
            "sales_achieved": json.dumps(sales_achieved),
        }

        return render(request, "index.html", context)

    except Exception as e:
        return HttpResponse(f"Exception: {str(e)}")

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

            #messages.success(request, "Lead updated successfully.")

 
        # CREATE LEAD
   
        else:
            lead = Lead.objects.create(**form_data,lead_created_by=request.user )

            #messages.success(request, "Lead created successfully.")

        # ManyToMany update
        lead.assigned_to.set(valid_users)

        
        # SAFE REDIRECT LOGIC
        collapse_hash = f"#collapse{lead.id}"
        viewlead_url = reverse("ViewLead")
        

        # Converted → go to converted tab
        if lead.status == "won":
            return redirect( f"{viewlead_url}?status=won{collapse_hash}")

        if next_url and next_url != "None":
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
        "REGION_CHOICES" : Lead.REGION_CHOICES,
        
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
    users = User.objects.filter(profile__role="SALESMAN")
    next_url = request.GET.get("next") or request.POST.get("next")

    if not request.user.profile.is_admin:
        return redirect("dashboard")

    deal = getattr(lead, "deal", None)

    if request.method == "POST":

        deal_value = Decimal(request.POST.get("deal_value") or 0)
        closing_date = request.POST.get("closing_date")
        notes = request.POST.get("notes")
        userId = request.POST.get("salesman")

        if deal:
            deal.deal_value = deal_value
            deal.closing_date = closing_date
            deal.notes = notes
            deal.salesman_id = userId
            deal.save()
        else:
            deal = Deal.objects.create(
                lead=lead,
                deal_value=deal_value,
                closing_date=closing_date,
                notes=notes,
                salesman_id=userId,
                created_by=request.user
            )

        # 🔥 SYNC LOGIC (IMPORTANT)
        if userId:
            # ensure in assigned_to (ManyToMany)
           deal.lead.assigned_to.set([userId])
        deal.update_payment_status()

        if next_url:
            url = f"#collapse{deal.lead.id}"
            return redirect(next_url + url)

    return render(request, "CreateDeal.html", {
        "lead": lead,
        "deal": deal,
        "users": users
    })
@login_required
def UpdateDeal(request, deal_id):

    deal = get_object_or_404(Deal, id=deal_id)
    next_url = request.GET.get("next") or request.POST.get("next")
    users = User.objects.filter(profile__role="SALESMAN")

    if not request.user.profile.is_admin:
        return redirect("dashboard")

    if request.method == "POST":

        deal_value = Decimal(request.POST.get("deal_value") or deal.deal_value)
        closing_date = request.POST.get("closing_date") or deal.closing_date
        notes = request.POST.get("notes")
        userId = request.POST.get("salesman")

        # ✅ Update deal
        deal.deal_value = deal_value
        deal.closing_date = closing_date
        deal.notes = notes
        deal.salesman_id = userId

        deal.save()

        # ✅ Update ManyToMany table ONLY
        if userId:
            deal.lead.assigned_to.set([userId])

        deal.update_payment_status()

        if next_url:
            url = f"#collapse{deal.lead.id}"
            return redirect(next_url + url)

    return render(request, "CreateDeal.html", {
        "deal": deal,
        "lead": deal.lead,
        "users": users
    })

@login_required
def AddInstallment(request, deal_id):

    deal = get_object_or_404(Deal, id=deal_id)

    if not request.user.profile.is_admin:
        messages.error(request, "Unauthorized access")
        return redirect("dashboard")

    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":

        amount_input = request.POST.get("amount")
        note = request.POST.get("note")
        payment_date_str = request.POST.get("payment_date")
        payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()


        try:
            amount = Decimal(amount_input)
        except (InvalidOperation, TypeError):
            messages.error(request, "Invalid amount format")
            return redirect(request.path)

        if amount <= 0:
            messages.error(request, "Amount must be greater than 0")
            return redirect(request.path)

        current_total = deal.installments.aggregate(
            total=Sum("amount")
        )["total"] or 0

        new_total = current_total + amount
        deal_value = deal.deal_value

        if new_total > deal_value:
            remaining = deal_value - current_total

            messages.error(
                request,
                f"Amount exceeds deal limit. You can only add Rs {remaining}"
            )
            return redirect(request.path)

 
        DealInstallment.objects.create(
            deal=deal,
            amount=amount,
            note=note,
            payment_date=payment_date,
            created_by=request.user
        )

 
        if hasattr(deal, "update_payment_status"):
            deal.update_payment_status()

            messages.success(request, "Installment added successfully")

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
        messages.error(request, "Unauthorized access")
        return redirect("dashboard")

    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":

        amount_input = request.POST.get("amount")
        payment_date_str = request.POST.get("payment_date")
        payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()


        try:
            new_amount = Decimal(amount_input)
        except (InvalidOperation, TypeError):
            messages.error(request, "Invalid amount format")
            return redirect(request.path)

        if new_amount <= 0:
            messages.error(request, "Amount must be greater than 0")
            return redirect(request.path)

        other_total = installment.deal.installments.exclude(
            id=installment.id
        ).aggregate(total=Sum("amount"))["total"] or 0

        new_total = other_total + new_amount
        deal_value = installment.deal.deal_value

        if new_total > deal_value:
            remaining = deal_value - other_total

            messages.error(
                request,
                f"Amount exceeds limit. You can only add up to Rs {remaining}"
            )
            return redirect(request.path)

        old_amount = installment.amount

        installment.amount = new_amount
        installment.payment_date = payment_date
        if hasattr(installment, "updated_by"):
            installment.updated_by = request.user

        installment.save()


        messages.success(request, "Installment updated successfully")

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
        sales_leaderboard = Sales_Leader_board()
       
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
                updated_by=request.user 
            )

 
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
    print('revenue :', revenue)
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



def sales_chart_data(request):

    targets = SalesTarget.objects.select_related("user").order_by("year", "month")

    labels = []
    target_data = []
    achieved_data = []

    for t in targets:
        label = f"{t.user.username} - {t.get_month_display()}"
        labels.append(label)

        target_data.append(float(t.target_amount))
        achieved_data.append(float(t.achieved_amount))

    return JsonResponse({
        "labels": labels,
        "targets": target_data,
        "achieved": achieved_data
    })


def layout(request):
    try:
        return render(request,'layout.html')
    except Exception as e:
        return str(e)





def multi_user_sales_chart(request):

    users = User.objects.filter(profile__role="SALESMAN")

    months = [month_name[m] for m in range(1, 13)]

    # 🔥 SINGLE QUERY (VERY IMPORTANT)
    installments = DealInstallment.objects.filter(
        is_deleted=False
    ).values(
        "deal__salesman__username",
        "deal__lead__assigned_to__username",
        "payment_date__month"
    ).annotate(
        total=Sum("amount")
    )

    # 🔥 BUILD MAP
    data_map = {}

    for row in installments:
        month = row["payment_date__month"]
        amount = float(row["total"] or 0)

        # salesman
        if row["deal__salesman__username"]:
            key = (row["deal__salesman__username"], month)
            data_map[key] = data_map.get(key, 0) + amount

        # assigned_to
        if row["deal__lead__assigned_to__username"]:
            key = (row["deal__lead__assigned_to__username"], month)
            data_map[key] = data_map.get(key, 0) + amount

    # =========================
    # BUILD SERIES
    # =========================
    series = []

    for user in users:
        achieved_list = []

        for m in range(1, 13):
            achieved_list.append(
                data_map.get((user.username, m), 0)
            )

        series.append({
            "name": user.username,
            "data": achieved_list
        })
    print(series)
    return JsonResponse({
        "months": months,
        "series": series
    })