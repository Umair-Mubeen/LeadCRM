from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum

from .models import DealInstallment, Commission, SalesTarget


def get_commission_rate(achieved, target):
    if target == 0:
        return Decimal("0")

    if achieved >= target:
        return Decimal("5")
    elif achieved >= (target * Decimal("0.75")):
        return Decimal("3")

    return Decimal("0")


def recalculate_monthly_commissions(user, month, year):

    # =========================
    # 🎯 TARGET (INTEGER MONTH)
    # =========================
    target_obj = SalesTarget.objects.filter(
        user=user,
        month=month,   # INTEGER MATCH ✅
        year=year
    ).first()

    target = target_obj.target_amount if target_obj else Decimal("0")

    # =========================
    # 💰 INSTALLMENTS
    # =========================
    installments = DealInstallment.objects.filter(
        deal__created_by=user,
        payment_date__month=month,
        payment_date__year=year
    )

    # =========================
    # ❌ DELETE ONLY UNPAID
    # =========================
    Commission.objects.filter(
        installment__in=installments,
        is_paid=False
    ).delete()

    # =========================
    # 📊 ACHIEVED
    # =========================
    achieved = installments.aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")

    # =========================
    # 📈 RATE
    # =========================
    rate = get_commission_rate(achieved, target)

    # =========================
    # 💸 CREATE COMMISSIONS
    # =========================
    for inst in installments:

        # skip already paid commissions
        if Commission.objects.filter(
            installment=inst,
            user=user,
            is_paid=True
        ).exists():
            continue

        amount = (inst.amount * rate) / Decimal("100")

        if amount <= 0:
            continue

        Commission.objects.update_or_create(
            installment=inst,
            user=user,
            defaults={
                "percentage": rate,
                "amount": amount
            }
        )


@receiver(post_save, sender=DealInstallment)
def handle_installment_save(sender, instance, created, **kwargs):

    if not instance.payment_date:
        return

    user = instance.deal.created_by

    # 👇 THIS IS KEY (INTEGER MONTH)
    month = instance.payment_date.month
    year = instance.payment_date.year

    recalculate_monthly_commissions(user, month, year)