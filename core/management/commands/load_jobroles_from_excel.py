from django.core.management.base import BaseCommand
from core.models import JobRole
import pandas as pd

EXCEL_PATH  = r"D:\performance_eval\employees_normalized.xlsx"
SHEET_NAME  = "Sheet1"
ROLE_COL    = "job_role"          # ستونی که تو اسکرین‌هات نشان دادی

class Command(BaseCommand):
    help = "Load distinct JobRoles from Excel (create/update by name). Code stays empty to fill manually."

    def handle(self, *args, **opts):
        df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
        if ROLE_COL not in df.columns:
            self.stderr.write(self.style.ERROR(f"Column '{ROLE_COL}' not found in sheet!"))
            return

        roles = (df[ROLE_COL].astype(str).str.strip()
                 .replace({"nan": ""})
                 .dropna().drop_duplicates())
        created, touched = 0, 0
        for name in roles:
            if not name:
                continue
            obj, was_created = JobRole.objects.get_or_create(name=name)
            # کُد را دست نمی‌زنیم؛ برای ویرایش دستی
            touched += 1
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Loaded roles from Excel. distinct_in_file={touched}, created_new={created}"
        ))
