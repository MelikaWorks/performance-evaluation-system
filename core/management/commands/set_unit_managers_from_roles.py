# js/management/commands/set_unit_managers_from_roles.py
from __future__ import annotations

import re
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Unit, EmployeeProfile, Organization

# کلیدواژه‌های مدیر (نه رئیس/سرپرست)
MANAGER_CORE_PAT = re.compile(r"(?:^|\s)(مدیر|manager)(?:\s|$)", re.IGNORECASE)
# کلیدواژه‌های تقویتی (اگر وجود داشتند امتیاز بیشتر)
MANAGER_CONTEXT_PAT = re.compile(r"(واحد|دپارتمان|بخش|production|department|unit|factory)", re.IGNORECASE)
# چیزهایی که مدیر نیستند
NOT_MANAGER_PAT = re.compile(r"(سرپرست|سوپروایزر|رئیس|رییس|فرمانده|supervisor|chief|head)", re.IGNORECASE)

def score_as_unit_manager(title: str) -> int:
    if not title:
        return -10
    t = str(title)
    if NOT_MANAGER_PAT.search(t):
        return -10
    score = 0
    if MANAGER_CORE_PAT.search(t):
        score += 10
    if MANAGER_CONTEXT_PAT.search(t):
        score += 3
    # کلیدواژه‌های تقویتی متداول
    if re.search(r"(مدیر\s*واحد|unit\s*manager|department\s*manager|production\s*manager)", t, re.IGNORECASE):
        score += 5
    return score

class Command(BaseCommand):
    help = "Auto-set Unit.manager by finding *a single true unit manager* in that unit based on job_role text (robust heuristic)."

    def add_arguments(self, parser):
        parser.add_argument("--org", type=str, required=False, help="نام سازمان برای فیلتر")
        parser.add_argument("--prefer", type=str, required=False, help='الگوی ترجیح در چندکاندیدایی (مثلا: "مدیر واحد")')
        parser.add_argument("--dry-run", action="store_true", help="فقط گزارش، بدون ذخیره")

    def handle(self, *args, **opts):
        org_name = opts.get("org")
        prefer_pat = re.compile(opts["prefer"], re.IGNORECASE) if opts.get("prefer") else None
        dry_run = bool(opts.get("dry_run"))

        units = Unit.objects.select_related("organization", "manager").all()
        if org_name:
            try:
                org = Organization.objects.get(name=org_name)
            except Organization.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Organization not found: {org_name}"))
                return
            units = units.filter(organization=org)

        updated = skipped_none = skipped_multi = 0
        details_multi = []

        with transaction.atomic():
            for u in units:
                # همه‌ی پرسنل همین یونیت با job_role
                qs = EmployeeProfile.objects.select_related("user", "job_role").filter(unit=u, job_role__isnull=False)
                scored = []
                for ep in qs:
                    title = ep.job_role.name or ""
                    sc = score_as_unit_manager(title)
                    if sc > 0:
                        scored.append((sc, ep))

                if not scored:
                    skipped_none += 1
                    continue

                # مرتب‌سازی بر اساس امتیاز (بالاتر → بهتر)
                scored.sort(key=lambda p: (-p[0], p[1].personnel_code or ""))

                # اگر چند کاندید داریم و prefer pattern دادیم، تلاش برای انتخاب مطابق prefer
                pick = None
                if prefer_pat:
                    for sc, ep in scored:
                        if prefer_pat.search(ep.job_role.name or ""):
                            pick = ep
                            break
                if not pick:
                    # اگر چندتایی‌اند و اختلاف امتیاز کم است، برای جلوگیری از اشتباه، رد می‌کنیم
                    if len(scored) > 1 and scored[0][0] == scored[1][0]:
                        skipped_multi += 1
                        details_multi.append(u.name)
                        continue
                    pick = scored[0][1]

                if not dry_run:
                    if u.manager_id != pick.user_id:
                        u.manager = pick.user
                        u.save(update_fields=["manager"])
                        updated += 1

        self.stdout.write(self.style.SUCCESS(f"Unit.manager set: {updated}, skipped (no true manager): {skipped_none}, skipped (ambiguous): {skipped_multi}"))
        if skipped_multi:
            # فقط نام یونیت‌ها را چاپ می‌کنیم تا خروجی شلوغ نشود
            self.stdout.write(self.style.WARNING("Ambiguous units: " + ", ".join(details_multi[:30]) + (" ..." if len(details_multi) > 30 else "")))
