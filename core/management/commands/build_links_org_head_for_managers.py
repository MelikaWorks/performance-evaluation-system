from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from core.models import Organization, Unit, EmployeeProfile, EvaluationLink

def norm(s):
    if not s: return ""
    return str(s).replace("\u200c"," ").replace("\u00a0"," ").strip()

class Command(BaseCommand):
    help = "Add ORG_HEAD links for managers only (unit managers or job_role contains 'مدیر')."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Organization exact name")
        parser.add_argument("--head-pcode", required=True, help="Org head personnel_code (username)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        org_name = opts["org"]; head = opts["head_pcode"]; dry = opts["dry_run"]
        try:
            org = Organization.objects.get(name=org_name)
        except Organization.DoesNotExist:
            raise CommandError(f"Organization '{org_name}' not found.")
        try:
            head_user = User.objects.get(username=head)
        except User.DoesNotExist:
            raise CommandError(f"Head user '{head}' not found.")

        unit_manager_ids = set(Unit.objects.filter(organization=org, manager__isnull=False)
                                    .values_list("manager_id", flat=True))
        role_pairs = EmployeeProfile.objects.filter(organization=org, job_role__isnull=False)\
                                           .values_list("user_id","job_role__name")
        role_manager_ids = {uid for (uid, jr) in role_pairs if "مدیر" in norm(jr) or "مدير" in norm(jr)}
        manager_ids = (unit_manager_ids | role_manager_ids) - {head_user.id}

        c_new = c_upd = 0
        with transaction.atomic():
            for u in User.objects.filter(id__in=manager_ids):
                obj, created = EvaluationLink.objects.update_or_create(
                    organization=org, subordinate=u,
                    link_type=EvaluationLink.LinkType.ORG_HEAD,
                    defaults={"evaluator": head_user},
                )
                if created: c_new += 1
                else:       c_upd += 1
            if dry:
                transaction.set_rollback(True)

        prefix = "Dry-run; " if dry else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}ORG_HEAD for managers -> new:{c_new}, upd:{c_upd}"))
