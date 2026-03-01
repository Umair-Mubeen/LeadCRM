from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from django.conf import settings


class UserProfile(models.Model):

    ROLE_ADMIN = 'ADMIN'
    ROLE_SALESMAN = 'SALESMAN'
    ROLE_LGS = 'LGS'

    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_SALESMAN, 'Sales Man'),
        (ROLE_LGS, 'Lead Generation Specialist'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_SALESMAN,
        db_index=True
    )
    
   
    commission_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00
    )


    commission_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=500.00
    )

    def save(self, *args, **kwargs):

        # Auto set default commission based on role
        if self.role == self.ROLE_LGS:
            self.commission_percentage = Decimal("1.00")

        elif self.role == self.ROLE_SALESMAN:
            self.commission_percentage = Decimal("5.00")

        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN

    @property
    def is_salesman(self):
        return self.role == self.ROLE_SALESMAN

    @property
    def is_lgs(self):
        return self.role == self.ROLE_LGS


class Lead(models.Model):

    SOURCE_CHOICES = [
        ('bark', 'Bark'),
        ('upwork', 'UpWork'),
        ('thumbtack', 'Thumb Tack'),
        ('website', 'Website'),
        ('facebook', 'Facebook'),
        ('google', 'Google'),
        ('referral', 'Referral'),
        ('campaign', 'Campaign'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('qualified', 'Qualified'),
        ('proposal', 'Proposal Sent'),
        ('negotiation', 'Negotiation'),
        ('won', 'Won'),
        ('lost', 'Lost'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

     # Lead Information 
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField()
    mobile_number = models.CharField(max_length=100)
    company_name = models.CharField(max_length=100, blank=True, null=True)

    # Lead Details
    source = models.CharField(
        max_length=50,
        choices=SOURCE_CHOICES
    )

    region = models.CharField(max_length=50, blank=True, null=True)
    domain_name = models.URLField(blank=True, null=True)
    social_accounts = models.TextField(blank=True, null=True)

    budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True
    )

    requirements = models.TextField(blank=True, null=True)
    lead_brief = models.TextField(blank=True, null=True)

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='new'
    )

    #Lead Assigned to Which SalesMan
    assigned_to = models.ManyToManyField(
        User,
        blank=True,
        related_name="assigned_leads"
    )

    lead_created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads_created"
    )

    
    is_deleted = models.BooleanField(default=False)

    date_added = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_contacted = models.DateTimeField(blank=True, null=True)

    
    class Meta:
        ordering = ['-date_added']

        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['source']),
            models.Index(fields=['date_added']),
            models.Index(fields=['is_deleted']),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=['email', 'mobile_number'],
                name='unique_lead_identity'
            )
        ]

    
    def __str__(self):
        return self.full_name

   
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_converted(self):
        return self.status == "won"

    @property
    def latest_followup(self):
        return self.lead_followups.order_by("-created_at").first()

    def is_assigned_to(self, user):
        return self.assigned_to.filter(id=user.id).exists()

    def get_status_badge(self):
        mapping = {
            "new": "primary",
            "contacted": "warning",
            "qualified": "info",
            "proposal": "secondary",
            "negotiation": "dark",
            "won": "success",
            "lost": "danger",
        }
        return mapping.get(self.status, "secondary")

class LeadFollowUp(models.Model):

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="lead_followups"
    )

    note = models.TextField()

    next_followup_date = models.DateField(
        null=True,
        blank=True,
        db_index=True
    )

    is_completed = models.BooleanField(default=False, db_index=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="followups_created"
    )

    status_at_time = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['next_followup_date']),
            models.Index(fields=['is_completed']),
        ]

    def __str__(self):
        return f"{self.lead.full_name} - {self.created_by}"

    def save(self, *args, **kwargs):

        if not self.status_at_time:
            self.status_at_time = self.lead.status

        super().save(*args, **kwargs)

       
        self.lead.last_contacted = timezone.now()
        self.lead.save(update_fields=["last_contacted"])



class LeadStatusHistory(models.Model):

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="status_history"
    )

    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)

    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="status_changes"
    )

    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['changed_at']),
        ]

    def __str__(self):
        return f"{self.lead.full_name} status changed"
    


class Deal(models.Model):

    lead = models.OneToOneField(
        "Lead",
        on_delete=models.CASCADE,
        related_name="deal"
    )

    deal_value = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    # ==============================
    # PAYMENT STATUS
    # ==============================
    PAYMENT_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
    ]

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default='pending',
        db_index=True
    )

    # ==============================
    # NEW FIELD → PARTIAL PAYMENT
    # ==============================
    
    closing_date = models.DateField()

    payment_date = models.DateField(
        null=True,
        blank=True
    )

    notes = models.TextField(
        blank=True,
        null=True
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="deals_created"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_status']),
            models.Index(fields=['closing_date']),
        ]

    def __str__(self):
        return f"{self.lead.full_name} - ${self.deal_value}"

    # ==============================
    # BUSINESS PROPERTIES
    # ==============================

    @property
    def is_paid(self):
        return self.payment_status == "paid"

    @property
    def is_partial(self):
        return self.payment_status == "partial"

    @property
    def remaining_amount(self):
        return self.deal_value - self.amount_paid

    @property
    def formatted_value(self):
        return f"${self.deal_value:,.2f}"

    @property
    def amount_paid(self):
        total = self.installments.aggregate(
            total=models.Sum("amount")
        )["total"]
        return total or Decimal("0.00")
    
    @property
    def payment_percentage(self):
        if self.deal_value == 0:
            return 0
        return round((self.amount_paid / self.deal_value) * 100, 2)

    # ==============================
    # AUTO PAYMENT STATUS HANDLER
    # ==============================
    def update_payment_status(self):

        if self.amount_paid <= Decimal("0"):
            self.payment_status = "pending"
            self.payment_date = None

        elif self.amount_paid < self.deal_value:
            self.payment_status = "partial"
            self.payment_date = None

        else:
            self.payment_status = "paid"
            self.payment_date = timezone.now().date()

        self.save()

class Commission(models.Model):

    deal = models.OneToOneField(
        Deal,
        on_delete=models.CASCADE,
        related_name="commission"
    )

    salesman = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="commissions"
    )

    commission_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    commission_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.salesman.username} - ${self.commission_amount}"
    

class DealInstallment(models.Model):

    deal = models.ForeignKey(
        "Deal",
        on_delete=models.CASCADE,
        related_name="installments"
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    payment_date = models.DateField(
        default=timezone.now
    )

    note = models.TextField(
        blank=True,
        null=True
    )

    # ✅ NEW FIELD
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="installments_created"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.deal.lead.full_name} - ${self.amount}"
