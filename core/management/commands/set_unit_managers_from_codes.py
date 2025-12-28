# js/management/commands/set_unit_managers_from_codes.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, List, Optional

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Organization, Unit, EmployeeProfile


def zfill_str(x: object, n: int = 3) -> str:
    """Normalize numbers stored as strings (e.g. '1', '01', '1.0') to zero-padded strings."""
    if x is None:
        return ""
    s = str(x).strip().replace(".0", "")
    return s.zfill(n)


def role_tag(v: object) -> str:
    """Map role_level to a stable tag (supports both 000–004 and 900–904)."""
    v3 = zfill_str(v, 3)
    if v3 in ("000", "900"):
        return "HEAD"          # مدیر کارخانه
    if v3 in ("001", "901"):
        return "UNIT_MGR"      # مدیر واحد
    if v3 in ("002", "902"):
        return "SECTION_HEAD"  # رئیس
    if v3 in ("003", "903"):
        return "SUPERVISOR"    # سرپرست
    if v3 in ("004", "904"):
        return "STAFF"         # کارمند
    return "OTHER"


@dataclass(frozen=True)
class MissingRow:
    org: str
    unit: str
    personnel_code: str
    reason: str


class Command(BaseCommand):
    help = (
        "ست‌کردن Unit.manager از روی اکسل بر اساس role_level.\n"
        "از هر دو طرح کدنویسی 000–004 و 900–904 پشتیبانی می‌کند و برای هر (org, unit)\n"
        "کاندیدای مدیر واحد (UNIT_MGR) را با کمترین team_code انتخاب می‌کند."
    )

    def add_arguments(self, parser):
        parser.add_argument("excel", type=str, help="مسیر فایل اکسل")
        parser.add_argument("--sheet", type=str, default="Sheet1", help="نام شیت (پیش‌فرض: Sheet1)")
        parser.add_argument("--org", type=str, required=False, help="فقط همین سازمان ایمپورت شود")

    def _ensure_columns(self, df: pd.DataFrame, must_have: List[str]) -> pd.DataFrame:
        missing = [c for c in must_have if c not in df.columns]
        if missing:
            raise CommandError(f"Missing required columns: {missing}")
        # strip و یکنواخت‌سازی
        for c in must_have:
            df[c] = df[c].astype(str).str.strip()
        return df

    def handle(self, *args, **opts):
        excel: str = opts["excel"]
        sheet: str = opts["sheet"]
        org_filter: Optional[str] = opts.get("org") or None

        # 1) خواندن اکسل
        try:
            df = pd.read_excel(excel, sheet_name=sheet, dtype=str).fillna("")
        except Exception as e:
            raise CommandError(f"Cannot read Excel '{excel}': {e}")

        df = self._ensure_columns(
            df,
            ["organization", "unit", "personnel_code", "role_level", "team_code"],
        )

        # 2) نرمال‌سازی role_level و ساخت role_tag
        df = df.assign(
            role_level=df["role_level"].map(lambda x: zfill_str(x, 3)),
            team_code=df["team_code"].astype(str).str.strip(),
        )
        df["role_tag"] = df["role_level"].map(role_tag)

        if org_filter:
            df = df[df["organization"] == org_filter]
            if df.empty:
                self.stdout.write(self.style.WARNING(f"No rows for organization '{org_filter}' in sheet '{sheet}'."))
                return

        # فقط مدیران واحد
        mgrs = df[df["role_tag"] == "UNIT_MGR"].copy()
        if mgrs.empty:
            self.stdout.write(self.style.WARNING("No rows with UNIT_MGR role found (001/901)."))
            return

        # برای سورت امن: تلاش برای تبدیل team_code به عدد؛ اگر نشد، از رشته استفاده می‌کنیم
        # (به این ترتیب '2' < '10' درست عددی رفتار می‌کند)
        mgrs["_team_code_num"] = pd.to_numeric(mgrs["team_code"], errors="coerce")
        mgrs = mgrs.sort_values(by=["organization", "unit", "_team_code_num", "team_code"])

        # 3) پیش‌بارگذاری اشیاء DB برای کاهش کوئری‌ها و هشدارها
        org_names = sorted(mgrs["organization"].unique().tolist())
        unit_pairs: List[Tuple[str, str]] = sorted(mgrs[["organization", "unit"]].drop_duplicates().itertuples(index=False, name=None))
        pcodes = sorted(mgrs["personnel_code"].unique().tolist())

        org_map: Dict[str, Organization] = {o.name: o for o in Organization.objects.filter(name__in=org_names)}
        unit_map: Dict[Tuple[str, str], Unit] = {}
        for org_name, unit_name in unit_pairs:
            org_obj = org_map.get(org_name)
            if org_obj:
                unit = Unit.objects.filter(organization=org_obj, name=unit_name).first()
                if unit:
                    unit_map[(org_name, unit_name)] = unit

        ep_map: Dict[str, EmployeeProfile] = {
            ep.personnel_code: ep for ep in EmployeeProfile.objects.filter(personnel_code__in=pcodes).select_related("user")
        }

        missing: List[MissingRow] = []
        set_count = 0

        # 4) انجام انتساب‌ها
        with transaction.atomic():
            # هر (org, unit) فقط اولین (کمترین team_code) انتخاب می‌شود
            for (org_name, unit_name), sub in mgrs.groupby(["organization", "unit"], sort=False):
                row = sub.iloc[0]
                unit = unit_map.get((org_name, unit_name))
                if not unit:
                    reason = "unit-not-found" if org_name in org_map else "org-not-found"
                    missing.append(MissingRow(org_name, unit_name, row["personnel_code"], reason))
                    continue

                ep = ep_map.get(row["personnel_code"])
                if not ep:
                    missing.append(MissingRow(org_name, unit_name, row["personnel_code"], "employeeprofile-not-found"))
                    continue

                # فقط در صورت تغییر، ذخیره کنیم
                if unit.manager_id != ep.user_id:
                    unit.manager = ep.user
                    unit.save(update_fields=["manager"])
                    set_count += 1

        self.stdout.write(self.style.SUCCESS(f"Unit.manager set/updated: {set_count}"))

        # 5) گزارش موارد ناموجود (خلاصه و خوانا)
        if missing:
            MAX_SHOW = 15
            preview = missing[:MAX_SHOW]
            tail = f" … (+{len(missing)-MAX_SHOW} more)" if len(missing) > MAX_SHOW else ""
            # هر آیتم به‌شکل فشرده چاپ می‌شود
            lines = [f"({m.org} / {m.unit}) pcode={m.personnel_code} → {m.reason}" for m in preview]
            self.stdout.write(self.style.WARNING("Missing references:\n - " + "\n - ".join(lines) + tail))
