from django.core.management.base import BaseCommand
from django.db import transaction
from collections import defaultdict
import pandas as pd

from core.models import JobRole, Unit

EXCEL_PATH = r"D:\performance_eval\employees_normalized.xlsx"
SHEET_NAME = "Sheet1"

# نام دقیق ستون‌ها را اگر فرق می‌کند، اینجا تنظیم کن
COL_ROLE = "job_role"
COL_UNIT = "unit_code"  # اگر ستون‌ت اسم دیگری دارد عوض کن

class Command(BaseCommand):
    help = "Sync JobRole.units from Excel (distinct pairs of job_role × unit_code)."

    @transaction.atomic
    def handle(self, *args, **opts):
        df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
        if COL_ROLE not in df.columns or COL_UNIT not in df.columns:
            self.stderr.write(self.style.ERROR(
                f"Columns '{COL_ROLE}' and/or '{COL_UNIT}' not found!"))
            return

        # role → set(unit_codes)
        buckets = defaultdict(set)
        for _, row in df[[COL_ROLE, COL_UNIT]].dropna().iterrows():
            role = str(row[COL_ROLE]).strip()
            ucode = str(row[COL_UNIT]).strip()
            if role and ucode:
                buckets[role].add(ucode)

        updated_roles = 0
        missing_units = []

        for role_name, codes in buckets.items():
            try:
                jr = JobRole.objects.get(name=role_name)
            except JobRole.DoesNotExist:
                # اگر JobRole هنوز با load_jobroles_from_excel ساخته نشده بود، رد می‌شویم
                continue

            # اگر مدل‌ت فیلد M2M ندارد، این بخش کار نمی‌کند
            if not hasattr(jr, "units"):
                self.stderr.write(self.style.WARNING(
                    f"JobRole '{role_name}' has no 'units' relation; skipped."))
                continue

            units = list(Unit.objects.filter(unit_code__in=codes))
            found_codes = {u.unit_code for u in units}
            for c in codes - found_codes:
                missing_units.append((role_name, c))

            jr.units.set(units)   # جایگزینی کامل لیست
            updated_roles += 1

        self.stdout.write(self.style.SUCCESS(
            f"JobRole.units synced. updated_roles={updated_roles}, missing_links={len(missing_units)}"
        ))
        if missing_units:
            self.stdout.write("Missing unit codes (no Unit found):")
            for role_name, code in missing_units[:30]:
                self.stdout.write(f"  {role_name} -> {code}")
            if len(missing_units) > 30:
                self.stdout.write(f"  ... and {len(missing_units)-30} more")
