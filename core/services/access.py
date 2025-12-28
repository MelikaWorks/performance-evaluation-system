# core/services/access.py
from django.contrib.auth.models import User
from core.models import EmployeeProfile, EvaluationLink

def visible_employee_profiles(user: User):
    try:
        prof = user.employee_profile
    except EmployeeProfile.DoesNotExist:
        return EmployeeProfile.objects.none()

    org = prof.organization

    # OrgAdmin: همهٔ سازمان
    if user.groups.filter(name="org_admin").exists():
        return EmployeeProfile.objects.filter(organization=org)

    # سایر نقش‌ها: هر کسی که کاربر ارزیابش است
    subs_ids = EvaluationLink.objects.filter(organization=org, evaluator=user)\
                                     .values_list("subordinate_id", flat=True)
    qs = EmployeeProfile.objects.filter(organization=org, user_id__in=subs_ids)

    # اگر هیچ زیردستی ندارد، خودش را ببیند (اختیاری)
    return qs if qs.exists() else EmployeeProfile.objects.filter(organization=org, user=user)
