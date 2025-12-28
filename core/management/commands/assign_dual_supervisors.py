from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import EmployeeProfile, Unit, Organization

# استثناها
NO_MANAGER_UNITS = {"حراست و انتظامات", "امور مالی", "حسابداری"}
LOGISTICS_UNIT = "لجستیک"

class Command(BaseCommand):
    help = "ست کردن همزمان مدیر و رئیس برای هر کارمند با درنظر گرفتن استثناها"

    def add_arguments(self, parser):
        parser.add_argument("--org", type=str, required=True, help="نام سازمان")
        parser.add_argument("--org-head", type=str, required=True, help="کد پرسنلی مدیر کارخانه (org head)")
        parser.add_argument("--dry-run", action="store_true", help="فقط گزارش بده، ذخیره نکن")

    def handle(self, *args, **opts):
        org_name = opts["org"]
        org_head_code = opts["org_head"]
        dry_run = opts["dry_run"]

        try:
            org = Organization.objects.get(name=org_name)
        except Organization.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Organization not found: {org_name}"))
            return

        try:
            org_head = EmployeeProfile.objects.get(personnel_code=org_head_code, organization=org).user
        except EmployeeProfile.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Org head personnel_code not found: {org_head_code}"))
            return

        updated = 0
        with transaction.atomic():
            for unit in Unit.objects.filter(organization=org).select_related("manager"):
                members = EmployeeProfile.objects.filter(unit=unit).select_related("user")

                # تعیین مدیر و رئیس بر اساس قوانین
                if unit.name == LOGISTICS_UNIT:
                    manager_user = org_head
                    section_head_user = None
                elif unit.name in NO_MANAGER_UNITS:
                    manager_user = None
                    # رئیس: کسی که role_level = 902 یا job_role شامل "رئیس"
                    section_head = members.filter(job_role__name__icontains="رئیس").first()
                    section_head_user = section_head.user if section_head else None
                else:
                    manager_user = unit.manager if unit.manager else None
                    section_head = members.filter(job_role__name__icontains="رئیس").first()
                    section_head_user = section_head.user if section_head else None

                for ep in members:
                    need_save = False
                    # ست کردن مدیر
                    if ep.unit and ep.unit.name not in NO_MANAGER_UNITS and manager_user:
                        if ep.direct_supervisor_id != manager_user.id:
                            ep.direct_supervisor = manager_user
                            need_save = True
                    elif ep.unit and ep.unit.name in NO_MANAGER_UNITS:
                        # این واحدها اصلاً مدیر ندارند
                        if ep.direct_supervisor_id is not None:
                            ep.direct_supervisor = None
                            need_save = True

                    # ست کردن رئیس (ستون جداگانه، فرض می‌کنیم فیلد custom داری: ep.section_head)
                    if hasattr(ep, "section_head"):
                        if section_head_user and ep.section_head_id != section_head_user.id:
                            ep.section_head = section_head_user
                            need_save = True
                        elif not section_head_user and ep.section_head_id is not None:
                            ep.section_head = None
                            need_save = True

                    if need_save and not dry_run:
                        ep.save()
                        updated += 1

        self.stdout.write(self.style.SUCCESS(f"Updated {updated} employee profiles"))
