from django.contrib.auth import get_user_model
from core.models import Unit, JobRole, EmployeeProfile

rows = [
    # (username, full_name, unit_code, role_code)
    ("213046", "مدیر واحد 213", "213", "901"),
    ("210019", "مدیر واحد 210", "210", "901"),
    ("114002", "مدیر واحد 114", "114", "901"),
    ("307031", "مدیر واحد 307", "307", "901"),
    ("212021", "مدیر واحد 212", "212", "901"),
    ("319006", "مدیر واحد 217", "217", "901"),
    ("218001", "مدیر واحد 218", "218", "901"),
    ("222003", "مدیر واحد 222", "222", "901"),
    ("508003", "مدیر واحد 202", "202", "901"),
    ("220001", "مدیر کارخانه 100", "100", "900"),
    ("215033", "رئیس واحد 213", "213", "902"),
    ("212039", "رئیس واحد 212", "212", "902"),
    ("212006", "رئیس واحد 216", "216", "902"),
    ("212040", "رئیس واحد 212", "212", "902"),
    ("213005", "رئیس واحد 212", "212", "902"),
    ("220002", "رئیس واحد 212", "212", "902"),
    ("206014", "رئیس واحد 202", "202", "902"),
    ("202033", "رئیس واحد 202", "202", "902"),
    ("212052", "رئیس واحد 222", "222", "902"),
    ("210046", "رئیس واحد 210", "210", "902"),
    ("212041", "رئیس واحد 114", "114", "902"),
    ("222006", "رئیس واحد 114", "114", "902"),
    ("319014", "رئیس واحد 202", "202", "902"),
    ("210045", "رئیس واحد 210", "210", "902"),
    ("224022", "رئیس واحد 210", "210", "902"),
    ("207003", "رئیس واحد 207", "207", "902"),
    ("210035", "رئیس واحد 210", "210", "902"),
]

User = get_user_model()
made_users = 0
made_profiles = 0

for username, full_name, unit_code, role_code in rows:
    username = str(username).strip()
    full_name = (full_name or "").strip()
    unit_code = str(unit_code).strip()
    role_code = str(role_code).strip()

    # 1) User
    u, created_u = User.objects.get_or_create(
        username=username,
        defaults={"is_active": True},
    )
    if created_u:
        made_users += 1
    u.set_password("123")
    if full_name and u.first_name != full_name:
        u.first_name = full_name
    u.save()

    # 2) Unit
    unit, _ = Unit.objects.get_or_create(
        unit_code=unit_code,
        defaults={"name": f"واحد {unit_code}"},
    )

    # 3) JobRole (اولین با این کُد؛ اگر نبود بساز)
    jr = JobRole.objects.filter(code=role_code).order_by("id").first()
    if not jr:
        jr, _ = JobRole.objects.get_or_create(
            name=f"نقش {role_code}",
            defaults={"code": role_code},
        )

    # 4) EmployeeProfile
    ep, created_ep = EmployeeProfile.objects.get_or_create(
        personnel_code=username,
        defaults={"user": u, "unit": unit, "job_role": jr},
    )
    if not created_ep:
        changed = False
        if ep.user_id != u.id:
            ep.user = u; changed = True
        if ep.unit_id != unit.id:
            ep.unit = unit; changed = True
        if ep.job_role_id != jr.id:
            ep.job_role = jr; changed = True
        if changed:
            ep.save()
    else:
        made_profiles += 1

print(f"DONE. users created: {made_users}, profiles created: {made_profiles}, total rows: {len(rows)}")

print(list(EmployeeProfile.objects.filter(
    personnel_code__in=["114002","220001","210035","213046","222006"]
).values_list("personnel_code","unit__unit_code","job_role__code")))
