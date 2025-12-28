from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from core.models import EmployeeProfile, Organization

@receiver(post_save, sender=User)
def create_employee_profile(sender, instance, created, **kwargs):
    if not created:
        return
    # فقط اگر یک organization داریم، همون رو ست کن؛ وگرنه فعلاً چیزی نساز
    org = Organization.objects.order_by("id").first()
    if not org:
        return
    EmployeeProfile.objects.get_or_create(
        user=instance,
        defaults={"organization": org}
    )
