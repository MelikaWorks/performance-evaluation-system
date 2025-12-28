from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import EmployeeProfile, Unit

class Command(BaseCommand):
    help = "Set EmployeeProfile.direct_supervisor from Unit.manager. Use --only-null to avoid overwriting existing."

    def add_arguments(self, parser):
        parser.add_argument("--only-null", action="store_true", help="Only fill when direct_supervisor is NULL")

    def handle(self, *args, **opts):
        only_null = opts["only_null"]
        updated = 0
        skipped_no_manager = 0
        skipped_self = 0

        with transaction.atomic():
            qs = EmployeeProfile.objects.select_related("unit", "user")
            if only_null:
                qs = qs.filter(direct_supervisor__isnull=True)

            for p in qs:
                if not p.unit or not p.unit.manager:
                    skipped_no_manager += 1
                    continue
                # مدیر خودش رئیس خودش نشه
                if p.user_id == p.unit.manager_id:
                    skipped_self += 1
                    continue
                if p.direct_supervisor_id != p.unit.manager_id:
                    p.direct_supervisor = p.unit.manager
                    p.save(update_fields=["direct_supervisor"])
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Updated: {updated}, Skipped(no unit/manager): {skipped_no_manager}, Skipped(self-manager): {skipped_self}"
        ))
