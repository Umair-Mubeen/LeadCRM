def calculate_commission(user, amount):
    if not hasattr(user, "profile"):
        return 0, 0

    percentage = user.profile.commission_percentage or 0
    commission_amount = (amount * percentage) / 100

    return percentage, commission_amount