# js/management/commands/backfill_reporting_lines.py
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import EmployeeProfile, ReportingLine

class Command(BaseCommand):
    help = "Create/Update ReportingLine from EmployeeProfile.direct_supervisor"

    def handle(self, *args, **kwargs):
        created = 0
        updated = 0
        skipped = 0

        with transaction.atomic():
            for p in EmployeeProfile.objects.select_related("organization", "user", "direct_supervisor"):
                if not p.direct_supervisor:
                    skipped += 1
                    continue
                rl, is_created = ReportingLine.objects.update_or_create(
                    organization=p.organization,
                    subordinate=p.user,
                    defaults={"supervisor": p.direct_supervisor},
                )
                if is_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created: {created}, Updated: {updated}, Skipped(no supervisor): {skipped}"
        ))
