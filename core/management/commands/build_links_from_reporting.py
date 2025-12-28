from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Organization, ReportingLine, EvaluationLink

def norm(s):
    if not s: return ""
    return str(s).replace("\u200c"," ").replace("\u00a0"," ").strip()

class Command(BaseCommand):
    help = "Build/Update EvaluationLink from ReportingLine for SECTION_HEAD and SUPERVISOR only."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Organization exact name")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        org_name = opts["org"]; dry = opts["dry_run"]
        try:
            org = Organization.objects.get(name=org_name)
        except Organization.DoesNotExist:
            raise CommandError(f"Organization '{org_name}' not found.")

        c_sec_new = c_sec_upd = 0
        c_sup_new = c_sup_upd = 0

        rels = ReportingLine.objects.select_related(
            "subordinate__employee_profile__job_role",
            "supervisor__employee_profile__job_role"
        ).filter(organization=org)

        with transaction.atomic():
            for rl in rels:
                sup_prof = getattr(rl.supervisor, "employee_profile", None)
                jr = norm(sup_prof.job_role.name) if (sup_prof and sup_prof.job_role) else ""

                if any(k in jr for k in ["رئیس","رييس","رییس"]):
                    obj, created = EvaluationLink.objects.update_or_create(
                        organization=org, subordinate=rl.subordinate,
                        link_type=EvaluationLink.LinkType.SECTION_HEAD,
                        defaults={"evaluator": rl.supervisor},
                    )
                    if created: c_sec_new += 1
                    else:       c_sec_upd += 1

                if "سرپرست" in jr:
                    obj, created = EvaluationLink.objects.update_or_create(
                        organization=org, subordinate=rl.subordinate,
                        link_type=EvaluationLink.LinkType.SUPERVISOR,
                        defaults={"evaluator": rl.supervisor},
                    )
                    if created: c_sup_new += 1
                    else:       c_sup_upd += 1

            if dry:
                transaction.set_rollback(True)

        prefix = "Dry-run; " if dry else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}SECTION(new:{c_sec_new}, upd:{c_sec_upd}) | SUPERVISOR(new:{c_sup_new}, upd:{c_sup_upd})"
        ))
