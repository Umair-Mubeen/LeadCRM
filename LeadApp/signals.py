from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import IntegrityError
from .models import DealInstallment, Commission


@receiver(post_save, sender=DealInstallment)
def create_commission_on_installment(sender, instance, created, **kwargs):

    if not created:
        return

    deal = instance.deal
    lead = deal.lead
    assigned_users = lead.assigned_to.all()

    for user in assigned_users:

        # Skip users without profile
        if not hasattr(user, "profile"):
            continue

        profile = user.profile
        percentage = profile.commission_percentage or Decimal("0")

        if percentage <= 0:
            continue

        commission_amount = (
            instance.amount * percentage
        ) / Decimal("100")

        try:
            Commission.objects.create(
                user=user,
                installment=instance,
                percentage=percentage,
                amount=commission_amount
            )
        except IntegrityError:
            # Prevent duplicate commission if signal fires twice
            pass