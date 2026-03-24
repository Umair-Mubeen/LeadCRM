from django.contrib import admin

# Register your models here.
from .models import SalesTarget

@admin.register(SalesTarget)
class SalesTargetAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "month",
        "year",
        "target_amount",
        "created_at"
    )

    list_filter = ("month", "year")



class CommissionAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "is_paid", "created_at")
    list_filter = ("is_paid",)