from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from core.models import Organization, EmployeeProfile, EvaluationLink

class Command(BaseCommand):
    help = "Add ORG_HEAD link ONLY for employees with NO EvaluationLink at all."

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

        all_ids = set(EmployeeProfile.objects.filter(organization=org).values_list("user_id", flat=True))
        linked_ids = set(EvaluationLink.objects.filter(organization=org).values_list("subordinate_id", flat=True))
        need_ids = (all_ids - linked_ids) - {head_user.id}

        c_new = 0
        with transaction.atomic():
            for uid in need_ids:
                u = User.objects.get(id=uid)
                EvaluationLink.objects.update_or_create(
                    organization=org, subordinate=u,
                    link_type=EvaluationLink.LinkType.ORG_HEAD,
                    defaults={"evaluator": head_user},
                )
                c_new += 1
            if dry:
                transaction.set_rollback(True)

        prefix = "Dry-run; " if dry else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Fallback ORG_HEAD created for {c_new} user(s)"))
