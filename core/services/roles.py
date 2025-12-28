#services/roles.py
from dataclasses import dataclass
from django.contrib.auth.models import User
from core.models import EmployeeProfile, Unit, ReportingLine

@dataclass(frozen=True)
class UserRoles:
    is_org_admin: bool = False
    is_unit_manager: bool = False
    is_supervisor: bool = False
    # اختیاری: نام نقش شغلی برای نمایش
    job_role_name: str | None = None

def get_user_roles(user: User) -> UserRoles:
    try:
        prof = user.employee_profile
        org = prof.organization
    except EmployeeProfile.DoesNotExist:
        return UserRoles()

    is_org_admin = user.groups.filter(name="org_admin").exists()

    # مدیر واحد اگر در هر واحدی manager باشد
    is_unit_manager = Unit.objects.filter(organization=org, manager=user).exists()

    # سرپرست اگر در ReportingLine کسی زیردستش باشد
    is_supervisor = ReportingLine.objects.filter(organization=org, supervisor=user).exists()

    job_role_name = prof.job_role.name if prof.job_role else None

    return UserRoles(
        is_org_admin=is_org_admin,
        is_unit_manager=is_unit_manager,
        is_supervisor=is_supervisor,
        job_role_name=job_role_name,
    )
