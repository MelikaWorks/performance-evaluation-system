# js/management/commands/build_evaluation_links.py
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from core.models import Organization, EmployeeProfile, Unit, ReportingLine, EvaluationLink

def clean_text(x: str) -> str:
    if not x:
        return ""
    return str(x).replace("\u200c", " ").replace("\u00a0", " ").strip()

class Command(BaseCommand):
    help = (
        "Build/Update EvaluationLink according to hierarchy:\n"
        "- DIRECT_SUPERVISOR from EmployeeProfile.direct_supervisor\n"
        "- UNIT_MANAGER from Unit.manager\n"
        "- SECTION_HEAD if supervisor's job_role name contains 'رئیس'\n"
        "- SUPERVISOR   if supervisor's job_role name contains 'سرپرست'\n"
        "- ORG_HEAD for managers and for any subordinate with no other link\n"
        "Use --types to choose which to build: DIRECT,UNIT_MANAGER,SECTION_HEAD,SUPERVISOR,ORG_HEAD"
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Organization exact name")
        parser.add_argument("--head-pcode", required=True, help="Org head personnel_code (username)")
        parser.add_argument("--dry-run", action="store_true", help="Preview without DB writes")
        parser.add_argument(
            "--types",
            help="Comma-separated link types to build: DIRECT,UNIT_MANAGER,SECTION_HEAD,SUPERVISOR,ORG_HEAD",
            default="",
        )

    def handle(self, *args, **opts):
        org_name = opts["org"]
        head_pcode = opts["head_pcode"]
        dry = opts["dry_run"]
        types_arg = (opts["types"] or "").strip().upper()
        requested = set(t.strip() for t in types_arg.split(",") if t.strip())
        # اگر --types ندهیم، هیچ نوعی ساخته نمی‌شود

        try:
            org = Organization.objects.get(name=org_name)
        except Organization.DoesNotExist:
            raise CommandError(f"Organization '{org_name}' not found.")
        try:
            org_head = User.objects.get(username=head_pcode)
        except User.DoesNotExist:
            raise CommandError(f"Head user '{head_pcode}' not found.")

        c = dict(
            created_direct=0,   updated_direct=0,
            created_unit=0,     updated_unit=0,
            created_sec=0,      updated_sec=0,
            created_sup=0,      updated_sup=0,
            created_head_mgr=0, updated_head_mgr=0,
            created_head_sub=0, updated_head_sub=0,
        )

        with transaction.atomic():
            # 1) DIRECT_SUPERVISOR
            if "DIRECT" in requested:
                qs = EmployeeProfile.objects.select_related("user", "direct_supervisor").filter(organization=org)
                for p in qs:
                    if p.direct_supervisor:
                        obj, created = EvaluationLink.objects.update_or_create(
                            organization=org,
                            subordinate=p.user,
                            link_type=EvaluationLink.LinkType.DIRECT_SUPERVISOR,
                            defaults={"evaluator": p.direct_supervisor},
                        )
                        if created:
                            c["created_direct"] += 1
                        else:
                            c["updated_direct"] += 1

            # 2) UNIT_MANAGER
            if "UNIT_MANAGER" in requested:
                qs = EmployeeProfile.objects.select_related("user", "unit").filter(
                    organization=org, unit__isnull=False
                )
                for p in qs:
                    mgr = p.unit.manager
                    if mgr and mgr != p.user:
                        obj, created = EvaluationLink.objects.update_or_create(
                            organization=org,
                            subordinate=p.user,
                            link_type=EvaluationLink.LinkType.UNIT_MANAGER,
                            defaults={"evaluator": mgr},
                        )
                        if created:
                            c["created_unit"] += 1
                        else:
                            c["updated_unit"] += 1

            # 3) SECTION_HEAD / SUPERVISOR (از ReportingLine با توجه به job_role بالادست)
            rels = ReportingLine.objects.select_related(
                "subordinate__employee_profile__job_role",
                "supervisor__employee_profile__job_role"
            ).filter(organization=org)

            if "SECTION_HEAD" in requested or "SUPERVISOR" in requested:
                for rl in rels:
                    sub = rl.subordinate
                    sup = rl.supervisor
                    sup_prof = getattr(sup, "employee_profile", None)
                    jr_name = clean_text(sup_prof.job_role.name) if (sup_prof and sup_prof.job_role) else ""

                    if "SECTION_HEAD" in requested and any(k in jr_name for k in ("رئیس", "رييس", "رییس")):
                        obj, created = EvaluationLink.objects.update_or_create(
                            organization=org,
                            subordinate=sub,
                            link_type=EvaluationLink.LinkType.SECTION_HEAD,
                            defaults={"evaluator": sup},
                        )
                        if created:
                            c["created_sec"] += 1
                        else:
                            c["updated_sec"] += 1

                    if "SUPERVISOR" in requested and ("سرپرست" in jr_name):
                        obj, created = EvaluationLink.objects.update_or_create(
                            organization=org,
                            subordinate=sub,
                            link_type=EvaluationLink.LinkType.SUPERVISOR,
                            defaults={"evaluator": sup},
                        )
                        if created:
                            c["created_sup"] += 1
                        else:
                            c["updated_sup"] += 1

            # 4 + 5) ORG_HEAD (برای مدیرها + fallback)
            if "ORG_HEAD" in requested:
                # مدیرها = manager واحد + هرکس عنوان شغلی‌اش شامل «مدیر»
                unit_manager_ids = set(
                    Unit.objects.filter(organization=org, manager__isnull=False)
                        .values_list("manager_id", flat=True)
                )
                role_manager_pairs = EmployeeProfile.objects.filter(
                    organization=org, job_role__isnull=False
                ).values_list("user_id", "job_role__name")
                role_manager_ids = {
                    uid for (uid, jr) in role_manager_pairs
                    if ("مدیر" in clean_text(jr) or "مدير" in clean_text(jr))
                }
                manager_ids = (unit_manager_ids | role_manager_ids) - {org_head.id}

                # 4) ORG_HEAD برای مدیرها
                for u in User.objects.filter(id__in=manager_ids):
                    obj, created = EvaluationLink.objects.update_or_create(
                        organization=org,
                        subordinate=u,
                        link_type=EvaluationLink.LinkType.ORG_HEAD,
                        defaults={"evaluator": org_head},
                    )
                    if created:
                        c["created_head_mgr"] += 1
                    else:
                        c["updated_head_mgr"] += 1

                # 5) ORG_HEAD برای کسانی که هیچ لینکی ندارند (fallback)
                sub_ids_with_any = set(
                    EvaluationLink.objects.filter(organization=org)
                        .values_list("subordinate_id", flat=True)
                )
                all_user_ids = set(
                    EmployeeProfile.objects.filter(organization=org)
                        .values_list("user_id", flat=True)
                )
                need_head = (all_user_ids - sub_ids_with_any) - {org_head.id}
                for uid in need_head:
                    u = User.objects.get(id=uid)
                    obj, created = EvaluationLink.objects.update_or_create(
                        organization=org,
                        subordinate=u,
                        link_type=EvaluationLink.LinkType.ORG_HEAD,
                        defaults={"evaluator": org_head},
                    )
                    if created:
                        c["created_head_sub"] += 1
                    else:
                        c["updated_head_sub"] += 1

            # اگر Dry-run، همه چیز رول‌بک شود:
            if dry:
                transaction.set_rollback(True)

        # خلاصه
        prefix = "Dry-run; no changes written." if dry else "Links written."
        self.stdout.write(self.style.SUCCESS(prefix))
        self.stdout.write(
            f"DIRECT     -> created {c['created_direct']}, updated {c['updated_direct']}\n"
            f"UNIT_MGR   -> created {c['created_unit']},   updated {c['updated_unit']}\n"
            f"SECTION_HD -> created {c['created_sec']},    updated {c['updated_sec']}\n"
            f"SUPERVISOR -> created {c['created_sup']},    updated {c['updated_sup']}\n"
            f"ORG_HEAD(mgrs) -> created {c['created_head_mgr']}, updated {c['updated_head_mgr']}\n"
            f"ORG_HEAD(fallback) -> created {c['created_head_sub']}, updated {c['updated_head_sub']}"
        )
