# js/management/commands/rebuild_hierarchy_from_excel.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Organization, Unit, EmployeeProfile


# ====================== پیکربندی ======================
# نقش‌ها: فقط 900..904 معتبرند
HEAD_TAGS         = {"900"}  # مدیر کارخانه
UNIT_MGR_TAGS     = {"901"}  # مدیر واحد
SECTION_HEAD_TAGS = {"902"}  # رئیس
SUPERVISOR_TAGS   = {"903"}  # سرپرست
STAFF_TAGS        = {"904"}  # کارمند
VALID_ROLES       = HEAD_TAGS | UNIT_MGR_TAGS | SECTION_HEAD_TAGS | SUPERVISOR_TAGS | STAFF_TAGS

# قواعد واحدها بر اساس unit_code
UNIT_RULES: Dict[str, Dict] = {
    "216": {"no_manager": True,  "logistics": False, "head_teams": set()},          # حراست
    "202": {"no_manager": False, "logistics": False, "head_teams": {"001","002","003"}},  # منابع انسانی (مثال)
    "218": {"no_manager": True,  "logistics": False, "head_teams": set()},          # امور مالی (مثال)
    # "219": {"no_manager": True,  "logistics": False, "head_teams": set()},        # حسابداری (اگر کُد جدا دارد)
    # "205": {"no_manager": False, "logistics": True,  "head_teams": set()},        # لجستیک (اگر همه زیر مدیر کارخانه‌اند)
}
DEFAULT_RULE = {"no_manager": False, "logistics": False, "head_teams": set()}


# ====================== ابزار کمکی ======================
def z3(x: object) -> str:
    s = ("" if x is None else str(x)).strip().replace(".0", "")
    return s.zfill(3)

@dataclass
class Row:
    org: str
    unit_code: str
    pcode: str
    role: str  # سه رقمی
    team: str

def team_sort_key(team: str) -> Tuple[int, str]:
    try:
        return (int(team), team)
    except Exception:
        return (10**9, team or "")


# ====================== کامند ======================
class Command(BaseCommand):
    help = (
        "بازسازی سلسله‌مراتب (Unit.manager / section_head / direct_supervisor) از روی اکسل، "
        "صرفاً با سه کُد: unit_code + role_level + team_code (بدون اتکا به پیشوند کد پرسنلی یا نام واحد)."
    )

    def add_arguments(self, parser):
        parser.add_argument("excel", type=str, help="مسیر فایل اکسل نرمال‌شده")
        parser.add_argument("--sheet", type=str, default="Sheet1")
        parser.add_argument("--org", type=str, required=True, help="نام سازمان (دقیق مطابق DB)")
        parser.add_argument("--org-head", type=str, required=True, help="کد پرسنلی مدیر کارخانه (مثلاً 220001)")
        parser.add_argument("--dry-run", action="store_true", help="فقط گزارش بده، ذخیره نکن")

    def handle(self, *args, **opts):
        excel: str = opts["excel"]
        sheet: str = opts["sheet"]
        org_name: str = opts["org"]
        org_head_pcode: str = opts["org_head"]
        dry_run: bool = bool(opts.get("dry_run"))

        # ---------- 1) خواندن و اعتبارسنجی اکسل ----------
        try:
            df = pd.read_excel(excel, sheet_name=sheet, dtype=str).fillna("")
        except Exception as e:
            raise CommandError(f"Cannot read Excel: {e}")

        must = ["organization", "unit_code", "personnel_code", "role_level", "team_code"]
        miss = [c for c in must if c not in df.columns]
        if miss:
            raise CommandError(f"Missing required columns: {miss}")

        for c in must:
            df[c] = df[c].astype(str).str.strip()
        df["role_level"] = df["role_level"].map(z3)

        # فقط نقش‌های 900..904 مجازند
        bad_roles = sorted(set(df["role_level"]) - VALID_ROLES)
        if bad_roles:
            raise CommandError(f"Invalid role_level values (expect only 900..904): {bad_roles}")

        org_df = df[df["organization"] == org_name].copy()
        if org_df.empty:
            self.stdout.write(self.style.WARNING(f"No rows for org='{org_name}'"))
            return

        rows: List[Row] = [
            Row(
                org=r["organization"],
                unit_code=str(r["unit_code"]).strip(),
                pcode=str(r["personnel_code"]).strip(),
                role=str(r["role_level"]).strip(),
                team=str(r["team_code"]).strip(),
            )
            for _, r in org_df.iterrows()
        ]
        row_by_pcode: Dict[str, Row] = {r.pcode: r for r in rows}

        # ---------- 2) DB ----------
        try:
            org = Organization.objects.get(name=org_name)
        except Organization.DoesNotExist:
            raise CommandError(f"Organization not found in DB: {org_name}")

        try:
            org_head_user = EmployeeProfile.objects.get(organization=org, personnel_code=org_head_pcode).user
        except EmployeeProfile.DoesNotExist:
            raise CommandError(f"Org head personnel_code not found in DB: {org_head_pcode}")

        units_qs = Unit.objects.filter(organization=org)
        units_by_uc: Dict[str, Unit] = {
            str(getattr(u, "unit_code", "")).strip(): u for u in units_qs if getattr(u, "unit_code", None)
        }

        pcodes = [r.pcode for r in rows]
        ep_by_pcode: Dict[str, EmployeeProfile] = {
            ep.personnel_code: ep
            for ep in EmployeeProfile.objects.filter(organization=org, personnel_code__in=pcodes).select_related("user", "unit")
        }

        # ---------- 3) نگاشت‌های صرفاً با unit_code + team_code ----------
        # مدیر واحد: unit_code -> EP (نخستین 901 با کمترین team_code)، مگر no_manager=true
        mgr_by_uc: Dict[str, EmployeeProfile] = {}
        # رئیس پایه: unit_code -> EP (کمترین team_code از 902)
        head_base_by_uc: Dict[str, EmployeeProfile] = {}
        # رئیس هم‌تیم: (unit_code, team_code) -> EP
        head_by_uc_team: Dict[Tuple[str, str], EmployeeProfile] = {}

        # مدیر واحدها
        for uc in set(r.unit_code for r in rows):
            rules = UNIT_RULES.get(uc, DEFAULT_RULE)
            if rules["no_manager"]:
                continue
            cands = [r for r in rows if r.unit_code == uc and r.role in UNIT_MGR_TAGS]
            if not cands:
                continue
            cands.sort(key=lambda x: team_sort_key(x.team))
            ep = ep_by_pcode.get(cands[0].pcode)
            if ep:
                mgr_by_uc[uc] = ep

        # رئیس‌ها (پایه و هم‌تیم)
        for r in rows:
            if r.role in SECTION_HEAD_TAGS:
                ep = ep_by_pcode.get(r.pcode)
                if ep:
                    head_by_uc_team[(r.unit_code, r.team)] = ep

        for uc in set(r.unit_code for r in rows):
            cands = [r for r in rows if r.unit_code == uc and r.role in SECTION_HEAD_TAGS]
            if not cands:
                continue
            cands.sort(key=lambda x: team_sort_key(x.team))
            ep = ep_by_pcode.get(cands[0].pcode)
            if ep:
                head_base_by_uc[uc] = ep

        # (اختیاری) هشدار اگر team_code رئیس خارج از head_teams پیکربندی شده باشد
        for (uc, t), ep in head_by_uc_team.items():
            allowed = UNIT_RULES.get(uc, DEFAULT_RULE)["head_teams"]
            if allowed and t not in allowed:
                self.stdout.write(self.style.WARNING(
                    f"Head team_code '{t}' for unit_code={uc} is not in allowed head_teams {allowed} (using anyway)"
                ))

        # ---------- 4) اعمال ----------
        upd_unit_mgr = 0
        upd_emp = 0

        with transaction.atomic():
            # 4.1) Unit.manager فقط با unit_code
            for uc, ep in mgr_by_uc.items():
                u = units_by_uc.get(uc)
                if not u:
                    continue
                if u.manager_id != ep.user_id:
                    if not dry_run:
                        u.manager = ep.user
                        u.save(update_fields=["manager"])
                    upd_unit_mgr += 1

            # 4.2) اعضا
            members = list(EmployeeProfile.objects.filter(organization=org).select_related("user", "unit"))
            for ep in members:
                row = row_by_pcode.get(ep.personnel_code)
                if not row:
                    continue  # این نفر در اکسل نیست/این سازمان نیست

                uc   = row.unit_code
                role = row.role
                team = row.team

                u = units_by_uc.get(uc)
                if not u:
                    continue

                rules = UNIT_RULES.get(uc, DEFAULT_RULE)
                no_mgr = rules["no_manager"]
                is_logi = rules["logistics"]

                # مدیر/رئیس‌های همین unit_code
                mgr_ep = mgr_by_uc.get(uc)
                mgr_user = None if no_mgr else (mgr_ep.user if mgr_ep else None)

                head_base_ep = head_base_by_uc.get(uc)
                head_base_user = head_base_ep.user if head_base_ep else None

                head_team_ep = head_by_uc_team.get((uc, team))
                head_team_user = head_team_ep.user if head_team_ep else None

                # پیش‌فرض
                new_direct = None
                new_section = None

                # 1) لجستیک → همه زیر مدیر کارخانه
                if is_logi:
                    new_direct = org_head_user
                    new_section = None

                # 2) واحدهای بدون مدیر
                elif no_mgr:
                    if role in SECTION_HEAD_TAGS:
                        # خودِ رئیس زیر مدیر کارخانه
                        new_direct = org_head_user
                        new_section = None
                    else:
                        # پرسنل: اول رئیس هم‌تیم؛ بعد رئیس پایه
                        new_direct = head_team_user or head_base_user
                        new_section = head_team_user or head_base_user

                # 3) سایر واحدها (مدیر دارند)
                else:
                    if role in HEAD_TAGS:
                        new_direct = None
                        new_section = None
                    elif role in UNIT_MGR_TAGS:
                        new_direct = org_head_user
                        new_section = None
                    elif role in SECTION_HEAD_TAGS:
                        new_direct = mgr_user
                        new_section = None
                    elif role in (SUPERVISOR_TAGS | STAFF_TAGS):
                        # پرسنل: اول رئیس هم‌تیم → بعد رئیس پایه → بعد مدیر واحد
                        new_direct = head_team_user or head_base_user or mgr_user
                        new_section = head_team_user or head_base_user
                    else:
                        # نقش ناشناخته → حداقل زیر مدیر واحد/رئیس پایه
                        new_direct = mgr_user or head_base_user
                        new_section = head_base_user

                need_save = False

                # اگر فیلدهای مجزا داریم (unit_manager/section_head)، مقداردهی میشود
                if hasattr(ep, "unit_manager_id"):
                    desired_um_id = None if no_mgr else (mgr_user.id if mgr_user else None)
                    if ep.unit_manager_id != desired_um_id:
                        ep.unit_manager = (mgr_user if desired_um_id else None)
                        need_save = True

                if hasattr(ep, "section_head_id"):
                    desired_sh_id = (new_section.id if new_section else None)
                    if ep.section_head_id != desired_sh_id:
                        ep.section_head = new_section
                        need_save = True

                desired_ds_id = (new_direct.id if new_direct else None)
                if ep.direct_supervisor_id != desired_ds_id:
                    ep.direct_supervisor = new_direct
                    need_save = True

                if need_save and not dry_run:
                    ep.save()
                if need_save:
                    upd_emp += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Unit.manager updated: {upd_unit_mgr}, employee updates: {upd_emp}"
        ))
