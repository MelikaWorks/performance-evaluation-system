# js/management/commands/set_direct_supervisors_from_units.py
from __future__ import annotations

from typing import  Optional, Set
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Organization, Unit, EmployeeProfile


class Command(BaseCommand):
    help = (
        "برای هر Unit که manager دارد، direct_supervisor همه اعضای آن Unit را به manager همان Unit ست می‌کند "
        "(به‌جز خودِ مدیر). امکان فیلتر سازمان/یونیت و only-null و dry-run دارد."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", type=str, required=False, help="نام سازمان (اختیاری)")
        parser.add_argument(
            "--exclude-units",
            type=str,
            required=False,
            help="لیست واحدها که نباید اعمال شوند (جدا با کاما). مثال: \"حراست و انتظامات,امور مالی,حسابداری\"",
        )
        parser.add_argument("--only-null", action="store_true", help="فقط کسانی که supervisor ندارند")
        parser.add_argument("--dry-run", action="store_true", help="فقط گزارش، بدون ذخیره")
        parser.add_argument("--workers-per-bulk", type=int, default=500, help="سایز bulk updates")

    def handle(self, *args, **opts):
        org_name: Optional[str] = opts.get("org")
        exclude_units_raw: Optional[str] = opts.get("exclude_units")
        only_null: bool = bool(opts.get("only_null"))
        dry_run: bool = bool(opts.get("dry_run"))
        bulk_size: int = int(opts.get("workers_per_bulk") or 500)

        exclude_units: Set[str] = set()
        if exclude_units_raw:
            exclude_units = {u.strip() for u in exclude_units_raw.split(",") if u.strip()}

        units_qs = Unit.objects.select_related("organization", "manager")
        if org_name:
            try:
                org = Organization.objects.get(name=org_name)
            except Organization.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Organization not found: {org_name}"))
                return
            units_qs = units_qs.filter(organization=org)

        # فقط یونیت‌هایی که manager دارند
        units_qs = units_qs.exclude(manager__isnull=True)

        total_targets = 0
        total_updated = 0
        total_skipped = 0

        with transaction.atomic():
            for u in units_qs.iterator():
                if u.name in exclude_units:
                    continue

                # اعضای یونیت (به‌جز خودِ مدیر)
                qs = EmployeeProfile.objects.filter(unit=u).exclude(user_id=u.manager_id)
                if only_null:
                    qs = qs.filter(direct_supervisor__isnull=True)

                ids = list(qs.values_list("id", flat=True))
                total_targets += len(ids)

                if dry_run or not ids:
                    continue

                # به صورت بچی آپدیت می‌کنیم
                start = 0
                while start < len(ids):
                    chunk = ids[start : start + bulk_size]
                    updated = EmployeeProfile.objects.filter(id__in=chunk).update(direct_supervisor=u.manager)
                    total_updated += updated
                    start += bulk_size

        total_skipped = total_targets - total_updated
        mode = "DRY-RUN" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"[{mode}] targets={total_targets}, updated={total_updated}, skipped={total_skipped}"))
