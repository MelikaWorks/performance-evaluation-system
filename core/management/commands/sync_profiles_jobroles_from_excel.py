# -*- coding: utf-8 -*-
import pandas as pd
from django.core.management.base import BaseCommand
from core.models import EmployeeProfile, JobRole, Unit

# نام ستون‌ها در اکسل (در صورت تفاوت، فقط این سه را عوض کن)
COL_PCODE = "personnel_code"
COL_ROLE  = "job_role"
COL_UNIT  = "unit_code"

def norm(s):
    if pd.isna(s):
        return ""
    s = str(s).strip()
    # تبدیل ارقام فارسی/عربی به انگلیسی
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return s.translate(trans)

class Command(BaseCommand):
    help = "Sync EmployeeProfile.job_role (and optionally unit) from Excel"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, required=True, help="Path to Excel")
        parser.add_argument("--sheet", type=str, default="Sheet1")
        parser.add_argument("--update-unit", action="store_true",
                            help="Also update EmployeeProfile.unit from Excel unit_code")

    def handle(self, *args, **opts):
        path  = opts["file"]
        sheet = opts["sheet"]
        do_unit = opts["update_unit"]

        df = pd.read_excel(path, sheet_name=sheet)

        # بررسی ستون‌ها
        for c in (COL_PCODE, COL_ROLE):
            if c not in df.columns:
                self.stderr.write(f"❌ Column '{c}' not found in sheet.")
                return
        if do_unit and COL_UNIT not in df.columns:
            self.stderr.write(f"❌ Column '{COL_UNIT}' not found but --update-unit given.")
            return

        # فقط ستون‌های لازم + تمیزکاری
        keep = [COL_PCODE, COL_ROLE] + ([COL_UNIT] if do_unit else [])
        df = df[keep].copy()
        df[COL_PCODE] = df[COL_PCODE].map(norm)
        df[COL_ROLE]  = df[COL_ROLE].map(lambda x: str(x).strip() if not pd.isna(x) else "")
        if do_unit:
            df[COL_UNIT] = df[COL_UNIT].map(norm)

        # حذف ردیف‌های بدون پرسنلی
        df = df[df[COL_PCODE] != ""]
        # اگر برای یک پرسنلی چند ردیف باشد، آخرین را نگه می‌داریم
        df = df.drop_duplicates(subset=[COL_PCODE], keep="last")

        updated, missing_profiles, created_roles, missing_units = 0, [], 0, set()

        # کشِ یونیت‌ها برای سرعت
        units_by_code = {}
        if do_unit:
            units_by_code = { (u.unit_code or "").strip(): u for u in Unit.objects.all().only("id", "unit_code") }

        for _, row in df.iterrows():
            pcode = row[COL_PCODE]
            role_name = row[COL_ROLE]
            unit_code = row[COL_UNIT] if do_unit else ""

            try:
                ep = EmployeeProfile.objects.get(personnel_code=pcode)
            except EmployeeProfile.DoesNotExist:
                missing_profiles.append(pcode)
                continue

            # نقش را بساز/بگیر و ست کن
            if role_name:
                jr, was_created = JobRole.objects.get_or_create(name=role_name)
                if was_created:
                    created_roles += 1
                ep.job_role = jr

            # در صورت نیاز، یونیت را هم هم‌راستا کن
            if do_unit and unit_code:
                u = units_by_code.get(unit_code)
                if not u:
                    missing_units.add(unit_code)
                else:
                    ep.unit = u

            ep.save(update_fields=["job_role"] + (["unit"] if do_unit else []))
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"✅ Profiles synced. updated={updated}, new_jobroles={created_roles}"
        ))
        if missing_profiles:
            self.stdout.write(self.style.WARNING(
                f"⚠️ Missing profiles for personnel_code: {', '.join(missing_profiles[:20])}"
            ))
            if len(missing_profiles) > 20:
                self.stdout.write(self.style.WARNING(f"... and {len(missing_profiles)-20} more"))
        if missing_units:
            sample = ", ".join(sorted(list(missing_units))[:20])
            self.stdout.write(self.style.WARNING(
                f"⚠️ Units not found for codes: {sample}"
            ))
