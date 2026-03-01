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
from .graph import RevenueGraph

from django.db import transaction
from django.contrib import messages

from .models import UserProfile, Lead, LeadFollowUp, LeadStatusHistory, Deal, Commission, DealInstallment

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
    monthly_revenue = RevenueGraph()
    print(monthly_revenue)
    

    if user.profile.is_admin or user.profile.is_lgs:
        leads = Lead.objects.filter(is_deleted=False)
        followups = LeadFollowUp.objects.filter(
            lead__is_deleted=False
        )
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

    conversion_rate = 0
    if total_leads > 0:
        conversion_rate = round((converted_leads / total_leads) * 100,2)

    deals = Deal.objects.all()

   
    total_revenue = deals.aggregate(total=Sum("deal_value"))["total"] or 0

    
    paid_revenue = deals.filter(payment_status="paid").aggregate(total=Sum("deal_value"))["total"] or 0

    
    pending_revenue = deals.filter(payment_status="pending").aggregate(total=Sum("deal_value"))["total"] or 0

    
    monthly_data = deals.annotate(month=TruncMonth("closing_date")).values("month").annotate(total=Sum("deal_value")).order_by("month")

    months = []
    revenues = []

    for item in monthly_data:
        months.append(item["month"].strftime("%b %Y"))
        revenues.append(float(item["total"]))

    total_commission = Commission.objects.aggregate(total=Sum("commission_amount"))["total"] or 0
    salesman_stats = deals.values("lead__assigned_to__username").annotate(total_revenue=Sum("deal_value"),total_deals=Count("id")).order_by("-total_revenue")

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
         "monthly_revenue": monthly_revenue
     
        
    }

    return render(request, "index.html", context)


@login_required
def ViewLead(request):

    user = request.user
    profile = user.profile
    status_filter = request.GET.get("status")
    priority_filter = request.GET.get("priority")

    base_queryset = Lead.objects.filter(is_deleted=False)

    if priority_filter:
        base_queryset = base_queryset.filter(priority=priority_filter)

    if status_filter:
        base_queryset = base_queryset.filter(status=status_filter)
    else:
        base_queryset = base_queryset.exclude(status="won")

  
    if not (profile.is_admin or profile.is_lgs):
        base_queryset = base_queryset.filter(assigned_to=user)

    
    leads = base_queryset.prefetch_related(Prefetch("lead_followups",queryset=LeadFollowUp.objects.order_by("-created_at")))

    return render(request, "view_lead.html", {"leads": leads})

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from django.contrib.auth.decorators import login_required

@login_required
@role_required([UserProfile.ROLE_ADMIN, UserProfile.ROLE_LGS])
@transaction.atomic
def AddEditLead(request, leadId=None):

    lead = None
    next_url = request.GET.get("next") or request.POST.get("next")

    # =========================
    # EDIT EXISTING LEAD
    # =========================
    if leadId:
        lead = get_object_or_404(
            Lead,
            id=leadId,
            is_deleted=False
        )

    # Salesman Users Only
    sales_users = User.objects.select_related("profile").filter(
        profile__role=UserProfile.ROLE_SALESMAN
    )

    if request.method == "POST":

        assigned_ids = request.POST.getlist("userId")

        # 🔒 Validate assigned users (Security)
        valid_users = User.objects.filter(
            id__in=assigned_ids,
            profile__role=UserProfile.ROLE_SALESMAN
        )

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
        }

        # =========================
        # UPDATE LEAD
        # =========================
        if lead:

            old_status = lead.status

            for field, value in form_data.items():
                setattr(lead, field, value)

            lead.save()

            # Track Status Change
            if old_status != lead.status:
                LeadStatusHistory.objects.create(
                    lead=lead,
                    old_status=old_status,
                    new_status=lead.status,
                    changed_by=request.user
                )

            messages.success(request, "Lead updated successfully.")

        # =========================
        # CREATE NEW LEAD
        # =========================
        else:

            lead = Lead.objects.create(
                **form_data,
                lead_created_by=request.user
            )

            messages.success(request, "Lead created successfully.")

        # Update ManyToMany
        lead.assigned_to.set(valid_users)

        # =========================
        # SMART REDIRECT LOGIC
        # =========================

        collapse_hash = f"#collapse{lead.id}"

        # If Converted → Go To Converted Tab
        if lead.status == "won":
            return redirect(
                f"{reverse('ViewLead')}?status=won{collapse_hash}"
            )

        # Preserve previous filter page
        if next_url:
            return redirect(f"{next_url}{collapse_hash}")

        # Default fallback
        return redirect(f"{reverse('ViewLead')}{collapse_hash}")

    # =========================
    # RENDER FORM
    # =========================
    return render(request, "createLead.html", {
        "lead": lead,
        "users": sales_users,
        "STATUS_CHOICES": Lead.STATUS_CHOICES,
        "PRIORITY_CHOICES": Lead.PRIORITY_CHOICES,
        "SOURCE_CHOICES": Lead.SOURCE_CHOICES,
        "next_url": next_url
    })


@login_required
def AddEditFollowup(request, lead_id, followup_id=None):

    lead = get_object_or_404(Lead, pk=lead_id, is_deleted=False)
    next_url = request.GET.get("next") or request.POST.get("next")
    user = request.user

    # Basic lead access check
    if not (
        user.profile.is_admin
        or user.profile.is_lgs
        or (user.profile.is_salesman and lead.is_assigned_to(user))
    ):
        raise PermissionDenied

    followup = None

    if followup_id:
        followup = get_object_or_404(
            LeadFollowUp,
            pk=followup_id,
            lead=lead
        )

        # 🔥 IMPORTANT: Salesman can edit ONLY his own followup
        if user.profile.is_salesman and followup.created_by != user:
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
    installment.delete()

    deal.update_payment_status()

    return redirect("ViewLead")