from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Organization, EmployeeProfile, EvaluationLink

class Command(BaseCommand):
    help = "Set EmployeeProfile.direct_supervisor to the closest evaluator: SUPERVISOR > SECTION_HEAD > UNIT_MANAGER > ORG_HEAD."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Organization exact name")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        org_name = opts["org"]; dry = opts["dry_run"]
        try:
            org_id = Organization.objects.only("id").get(name=org_name).id
        except Organization.DoesNotExist:
            raise CommandError(f"Organization '{org_name}' not found.")

        order = [
            "SUPERVISOR",
            "SECTION_HEAD",
            "UNIT_MANAGER",
            "DIRECT",
            "ORG_HEAD",
        ]
        prio = {t:i for i,t in enumerate(order)}

        updated = 0
        with transaction.atomic():
            qs = EmployeeProfile.objects.select_related("user","direct_supervisor").filter(organization_id=org_id)
            for p in qs:
                # همهٔ لینک‌های ارزیاب برای این نفر
                links = list(EvaluationLink.objects.filter(organization_id=org_id, subordinate=p.user)
                             .values_list("link_type","evaluator_id"))
                if not links:
                    continue
                # انتخاب نزدیک‌ترین
                links.sort(key=lambda t: prio.get(t[0], 999))
                best_eval_id = links[0][1]
                if p.direct_supervisor_id != best_eval_id:
                    p.direct_supervisor_id = best_eval_id
                    p.save(update_fields=["direct_supervisor"])
                    updated += 1

            if dry:
                transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(
            ("Dry-run; " if dry else "") + f"primary supervisors updated: {updated}"
        ))
