import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import JobRole, Unit

def norm_str(v):
    s = str(v).strip()
    # اعداد عربی/فارسی به انگلیسی
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return s.translate(trans)

class Command(BaseCommand):
    help = "Import JobRoles from Excel and attach them to Units (ManyToMany: allowed_units)"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, required=True,
                            help="Path to employees_normalized.xlsx")
        parser.add_argument("--sheet", type=str, default="Sheet1")

    @transaction.atomic
    def handle(self, *args, **opts):
        path  = opts["file"]
        sheet = opts["sheet"]

        df = pd.read_excel(path, sheet_name=sheet)

        COL_ROLE = "job_role"
        COL_UNIT = "unit_code"
        for c in (COL_ROLE, COL_UNIT):
            if c not in df.columns:
                self.stderr.write(f"❌ Column '{c}' not found in sheet.")
                return

        # فقط همین دو ستون + نرمال‌سازی + یکتا
        df = df[[COL_ROLE, COL_UNIT]].dropna()
        df[COL_ROLE] = df[COL_ROLE].map(norm_str)
        df[COL_UNIT] = df[COL_UNIT].map(norm_str)
        df = df[(df[COL_ROLE] != "") & (df[COL_UNIT] != "")]
        pairs = df.drop_duplicates()

        created_roles = 0
        links_added   = 0
        missing_units = set()

        # کش کردن یونیت‌ها برای سرعت
        all_units = { (str(u.unit_code or "").strip()): u for u in Unit.objects.all().only("id","unit_code") }

        for _, row in pairs.iterrows():
            role_name = row[COL_ROLE]
            ucode     = row[COL_UNIT]

            # نقش را بگیر/بساز
            jr, created = JobRole.objects.get_or_create(name=role_name)
            if created:
                created_roles += 1

            # یونیت را پیدا کن
            unit = all_units.get(ucode) or all_units.get(norm_str(ucode))
            if not unit:
                missing_units.add(ucode)
                continue

            # لینک ManyToMany (تکراری نشود)
            if not jr.allowed_units.filter(pk=unit.pk).exists():
                jr.allowed_units.add(unit)
                links_added += 1

        self.stdout.write(self.style.SUCCESS(
            f"✅ Import finished. new_roles={created_roles}, links_added={links_added}"
        ))
        if missing_units:
            miss = ", ".join(sorted(list(missing_units))[:30])
            more = len(missing_units) - min(len(missing_units), 30)
            self.stdout.write(self.style.WARNING(
                f"⚠️ Units not found for codes: {miss}{' ...' if more>0 else ''}"
            ))
