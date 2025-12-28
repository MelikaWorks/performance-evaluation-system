from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from core.models import Organization, EmployeeProfile, ReportingLine

class Command(BaseCommand):
    help = (
        "Link a list of personnel codes to the org head as their direct supervisor. "
        "Only affects the specified personnel codes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Organization name (exact match)")
        parser.add_argument("--head-pcode", required=True, help="Personnel code (username) of the org head")
        parser.add_argument("--subs", nargs="+", required=True, help="List of subordinate personnel codes (space separated)")
        parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to DB")

    def handle(self, *args, **opts):
        org_name = opts["org"]
        head_pcode = opts["head_pcode"]
        subs_pcodes = [str(x).strip() for x in opts["subs"]]
        dry = opts["dry_run"]

        try:
            org = Organization.objects.get(name=org_name)
        except Organization.DoesNotExist:
            raise CommandError(f"Organization '{org_name}' not found.")

        try:
            head_user = User.objects.get(username=head_pcode)
        except User.DoesNotExist:
            raise CommandError(f"Head user with personnel_code '{head_pcode}' not found.")

        # پیدا کردن یوزرهای زیرمجموعه از روی کد پرسنلی
        sub_users = []
        not_found = []
        for pc in subs_pcodes:
            try:
                sub_users.append(User.objects.get(username=pc))
            except User.DoesNotExist:
                not_found.append(pc)

        if not_found:
            self.stdout.write(self.style.WARNING(f"Personnel codes not found (skipped): {', '.join(not_found)}"))

        if not sub_users:
            self.stdout.write(self.style.WARNING("No valid subordinates to process."))
            return

        # پیش‌نمایش
        self.stdout.write(self.style.NOTICE(
            f"Will assign head '{head_user.get_full_name() or head_user.username}' "
            f"as direct_supervisor for {len(sub_users)} user(s) in org '{org_name}'."
        ))
        for u in sub_users[:10]:
            self.stdout.write(f"  - {u.username} | {u.first_name} {u.last_name}")

        if dry:
            self.stdout.write(self.style.WARNING("Dry-run mode: no changes written."))
            return

        updated_profiles = created_rl = updated_rl = 0
        with transaction.atomic():
            for u in sub_users:
                # sync EmployeeProfile (فقط اگر پروفایل در همان سازمان وجود داشته باشد)
                try:
                    p = EmployeeProfile.objects.get(user=u, organization=org)
                except EmployeeProfile.DoesNotExist:
                    # اگر پروفایل در این سازمان نیست، از این سازمان صرف‌نظر می‌کنیم
                    continue

                if p.user_id == head_user.id:
                    # مدیر کارخانه به خودش وصل نشود
                    continue

                if p.direct_supervisor_id != head_user.id:
                    p.direct_supervisor = head_user
                    p.save(update_fields=["direct_supervisor"])
                    updated_profiles += 1

                # Upsert ReportingLine
                rl, created_flag = ReportingLine.objects.update_or_create(
                    organization=org,
                    subordinate=u,
                    defaults={"supervisor": head_user},
                )
                if created_flag:
                    created_rl += 1
                else:
                    updated_rl += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Profiles updated: {updated_profiles}, ReportingLines created: {created_rl}, updated: {updated_rl}"
        ))
