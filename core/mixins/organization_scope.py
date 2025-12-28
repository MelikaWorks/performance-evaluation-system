from core.models import Organization, DepartmentGroup

class OrganizationScopedQuerysetMixin:
    """
    این میکسین داده‌های viewها را بر اساس جایگاه کاربر فیلتر می‌کند:
      - مدیر سایت → فقط داده‌های سازمان خودش
      - HR/IT مشترک → سازمان‌های گروه خودش
      - دفتر مرکزی → همه سازمان‌های holding خودش
      - سوپرادمین → همه‌چیز
    """

    def get_queryset(self):
        user = self.request.user

        # سوپرادمین: همه داده‌ها
        if user.is_superuser:
            return super().get_queryset()

        profile = getattr(user, "employeeprofile", None)
        if not profile:
            return super().get_queryset().none()

        qs = super().get_queryset()

        # دفتر مرکزی (فقط holding دارد)
        if profile.holding and not profile.organization and not profile.department_group:
            return qs.filter(holding=profile.holding)

        # HR یا IT مشترک
        if profile.department_group:
            allowed_orgs = profile.department_group.organizations.all()
            return qs.filter(organization__in=allowed_orgs)

        # مدیر یا کارمند یک سازمان/سایت
        if profile.organization:
            return qs.filter(organization=profile.organization)

        # حالت نامشخص
        return qs.none()

def scope_queryset(qs, user):
    """
    فیلتر داده‌ها بر اساس نقش کاربر:
      - سوپرادمین → همه
      - دفتر مرکزی → داده‌های holding
      - HR/IT مشترک → سازمان‌های گروه خودش
      - مدیر/کارمند → فقط سازمان خودش
    """
    # سوپرادمین
    if user.is_superuser:
        return qs

    profile = getattr(user, "employeeprofile", None)
    if not profile:
        return qs.none()

    # دفتر مرکزی
    if profile.holding and not profile.organization and not profile.department_group:
        return qs.filter(holding=profile.holding)

    # HR/IT مشترک
    if profile.department_group:
        allowed_orgs = profile.department_group.organizations.all()
        return qs.filter(organization__in=allowed_orgs)

    # مدیر یا کارمند کارخانه
    if profile.organization:
        return qs.filter(organization=profile.organization)

    return qs.none()
