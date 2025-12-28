# js/management/commands/assign_supervisors_from_codes.py
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Organization, Unit, EmployeeProfile
import pandas as pd

NO_MANAGER_UNITS = {"حراست و انتظامات", "امور مالی", "حسابداری"}  # واحدهایی که «مدیر واحد» ندارند و باید فقط به رئیس وصل شوند

def zfill_str(x, n=3):
    if x is None:
        return ""
    s = str(x).strip().replace(".0","", "")
    return s.zfill(n)

def role_tag(v: str) -> str:
    v3 = zfill_str(v, 3)
    if v3 in ("000", "900"): return "HEAD"         # مدیر کارخانه
    if v3 in ("001", "901"): return "UNIT_MGR"     # مدیر واحد
    if v3 in ("002", "902"): return "SECTION_HEAD" # رئیس
    if v3 in ("003", "903"): return "SUPERVISOR"   # سرپرست
    if v3 in ("004", "904"): return "STAFF"        # کارمند
    return "OTHER"

class Command(BaseCommand):
    help = "ست‌کردن direct_supervisor بر اساس role_level/واحد (پشتیبانی از 001/… و 901/… همزمان)"

    def add_arguments(self, parser):
        parser.add_argument("excel", type=str, help="مسیر فایل اکسل")
        parser.add_argument("--sheet", type=str, default="Sheet1")
        parser.add_argument("--org", type=str, required=False)
        parser.add_argument("--org-head", type=str, required=False, help="کد پرسنلی مدیر کارخانه برای fallback")
        parser.add_argument("--logistics-unit-name", type=str, required=False, help="نام واحد لجستیک (اختیاری)")

    def handle(self, *args, **opts):
        excel = opts["excel"]
        sheet = opts["sheet"]
        org_filter = opts.get("org")
        org_head_pcode = opts.get("org_head")
        logistics_unit = (opts.get("logistics_unit_name") or "").strip()

        try:
            df = pd.read_excel(excel, sheet_name=sheet, dtype=str).fillna("")
        except Exception as e:
            raise CommandError(f"Cannot read Excel: {e}")

        for c in ["organization","unit","personnel_code","role_level","team_code"]:
            if c not in df.columns:
                raise CommandError(f"Missing required column: {c}")
            df[c] = df[c].astype(str).str.strip()

        df["role_tag"] = df["role_level"].map(role_tag)
        if org_filter:
            df = df[df["organization"] == org_filter]

        # org-head
        org_head_user = None
        if org_head_pcode:
            try:
                org_head_user = EmployeeProfile.objects.get(personnel_code=org_head_pcode).user
            except EmployeeProfile.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"org-head personnel_code not found: {org_head_pcode}"))

        # رئیس هر واحد (SECTION_HEAD=902) برای 903/904
        # ...
        # leaders_by_unit: unit_name -> list[user] از نقش 902/002 (رئیس)
        leaders_by_unit = {}
        for pcode in df[df["role_tag"] == "SECTION_HEAD"]["personnel_code"].unique():
            try:
                ep = EmployeeProfile.objects.select_related("user", "unit").get(personnel_code=pcode)
                if ep.unit:
                    leaders_by_unit.setdefault(ep.unit.name, []).append(ep.user)
            except EmployeeProfile.DoesNotExist:
                pass

        updated, skipped = 0, 0

        for _, r in df.iterrows():
            pcode = r["personnel_code"]
            rtag = r["role_tag"]
            unit_name = r["unit"].strip()

            try:
                ep = EmployeeProfile.objects.select_related("unit", "user").get(personnel_code=pcode)
            except EmployeeProfile.DoesNotExist:
                skipped += 1
                continue

            # استثنای لجستیک: همیشه زیر مدیر کارخانه (اگر خواستی)
            if logistics_unit and ep.unit and ep.unit.name == logistics_unit and org_head_user:
                target = org_head_user

            # استثنای واحدهای «بدون مدیر»: حراست/مالی/حسابداری → فقط به رئیس وصل شوند؛ هیچ‌وقت به org-head نیفتند
            elif ep.unit and ep.unit.name in NO_MANAGER_UNITS:
                leaders = leaders_by_unit.get(unit_name, [])
                if rtag in ("HEAD", "UNIT_MGR"):
                    target = None  # این واحدها مدیر واحد ندارند؛ مدیر کارخانه هم نمی‌گذاریم
                elif rtag == "SECTION_HEAD":
                    target = None  # خودِ رئیس زیر کسی نباشد (یا اگر لازم است، می‌توان زیر org-head باشد)
                else:  # SUPERVISOR/STAFF
                    target = leaders[0] if leaders else None  # اگر رئیسی نیست، خالی بماند

            # سایر واحدها (روال عمومی)
            else:
                if rtag == "HEAD":
                    target = None
                elif rtag == "UNIT_MGR":
                    target = org_head_user  # مدیر واحد زیر مدیر کارخانه
                elif rtag == "SECTION_HEAD":
                    target = ep.unit.manager if ep.unit else None
                else:  # SUPERVISOR/STAFF
                    leaders = leaders_by_unit.get(unit_name, [])
                    target = leaders[0] if leaders else (ep.unit.manager if ep.unit else None)

            # اعمال
            if target is None:
                if ep.direct_supervisor_id is not None and rtag in ("HEAD", "SECTION_HEAD") | (
                        ep.unit and ep.unit.name in NO_MANAGER_UNITS):
                    ep.direct_supervisor = None
                    ep.save(update_fields=["direct_supervisor"])
                    updated += 1
            else:
                if ep.direct_supervisor_id != target.id:
                    ep.direct_supervisor = target
                    ep.save(update_fields=["direct_supervisor"])
                    updated += 1

        self.stdout.write(self.style.SUCCESS(f"direct_supervisor updated: {updated}, skipped: {skipped}"))

        @transaction.atomic
        def assign_all():
            nonlocal updated, skipped
            for _, r in df.iterrows():
                pcode = r["personnel_code"]
                rtag  = r["role_tag"]
                unit_name = r["unit"]
                try:
                    ep = EmployeeProfile.objects.select_related("unit","user").get(personnel_code=pcode)
                except EmployeeProfile.DoesNotExist:
                    skipped += 1
                    continue

                # لجستیک همیشه زیر org-head (اگر خواستی)
                if logistics_unit and ep.unit and ep.unit.name == logistics_unit and org_head_user:
                    target = org_head_user

                else:
                    if rtag == "HEAD":
                        target = None
                    elif rtag == "UNIT_MGR":
                        target = org_head_user  # مدیر واحد زیر مدیر کارخانه
                    elif rtag == "SECTION_HEAD":
                        target = ep.unit.manager if ep.unit else None
                    else:  # SUPERVISOR/STAFF
                        leaders = leaders_by_unit.get(unit_name, [])
                        target = (leaders[0] if leaders else (ep.unit.manager if ep.unit else None))

                # اعمال
                if target is None:
                    if ep.direct_supervisor_id is not None and rtag == "HEAD":
                        ep.direct_supervisor = None
                        ep.save(update_fields=["direct_supervisor"])
                        updated += 1
                else:
                    if ep.direct_supervisor_id != target.id:
                        ep.direct_supervisor = target
                        ep.save(update_fields=["direct_supervisor"])
                        updated += 1

        assign_all()
        self.stdout.write(self.style.SUCCESS(f"direct_supervisor updated: {updated}, skipped: {skipped}"))
