from django.apps import AppConfig


class LeadAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'LeadApp'   # 👈 MUST MATCH FOLDER NAME EXACTLY

    def ready(self):
        import LeadApp.signals