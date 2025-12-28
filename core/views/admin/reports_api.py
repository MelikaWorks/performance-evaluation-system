# core/views/admin/reports_api.py
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from core.models import Unit, EmployeeProfile, JobRole
from core.constants import Settings
from core.models import JobTitle


def _get_unit_by_id_or_code(raw):
    if not raw:
        return None
    # اول تلاش با id
    try:
        return Unit.objects.select_related("manager", "head").get(id=int(raw))
    except Exception:
        pass
    # سپس با unit_code
    return Unit.objects.select_related("manager", "head").filter(unit_code=str(raw)).first()

@staff_member_required
def get_managers_api(request):
    raw = request.GET.get("unit_id")
    unit = _get_unit_by_id_or_code(raw)
    if not unit:
        return JsonResponse({"results": []})

    qs = (
        EmployeeProfile.objects
        .filter(unit=unit, user__isnull=False)
        .select_related("user", "job_role")
    )

    results = []

    # مدیر کارخانه یا واحد
    for emp in qs:
        rc = (emp.job_role.code if emp.job_role else "")
        if rc in (Settings.ROLE_FACTORY_MANAGER, Settings.ROLE_UNIT_MANAGER):
            results.append({
                "id": emp.user_id,
                "name": emp.user.get_full_name() or emp.user.username,
                "role_code": rc,
            })

    # رئیس واحد
    for emp in qs:
        rc = (emp.job_role.code if emp.job_role else "")
        if rc == Settings.ROLE_SECTION_HEAD:
            results.append({
                "id": emp.user_id,
                "name": emp.user.get_full_name() or emp.user.username,
                "role_code": Settings.ROLE_SECTION_HEAD,
            })

    # اگر Unit.manager ست شده ولی در EP نبود
    if unit.manager and all(r["id"] != unit.manager_id for r in results):
        results.insert(0, {
            "id": unit.manager.id,
            "name": unit.manager.get_full_name() or unit.manager.username,
            "role_code": Settings.ROLE_UNIT_MANAGER,
        })

    # اگر Unit.head ست شده ولی در EP نبود
    if unit.head and all(r["id"] != unit.head_id for r in results):
        results.append({
            "id": unit.head.id,
            "name": unit.head.get_full_name() or unit.head.username,
            "role_code": Settings.ROLE_SECTION_HEAD,
        })

    # =============================================
    # ⭐ افزودن مدیر/رئیس فعلی کارمند به لیست نتایج
    # =============================================
    emp_id = request.GET.get("employee_id")
    same_unit = request.GET.get("same_unit") == "1"

    if emp_id and same_unit:
        ep = (
            EmployeeProfile.objects
            .filter(id=emp_id)
            .select_related("direct_supervisor", "section_head", "unit")
            .first()
        )

        if ep and ep.unit_id == unit.id:
            # مدیر فعلی (direct_supervisor) — فقط برای load اولیه و همان unit
            if ep.direct_supervisor and all(r["id"] != ep.direct_supervisor_id for r in results):
                results.insert(0, {
                    "id": ep.direct_supervisor_id,
                    "name": ep.direct_supervisor.get_full_name() or ep.direct_supervisor.username,
                    "role_code": ep.direct_supervisor.employee_profile.job_role.code,
                })

            # رئیس فعلی (section_head) — فقط برای load اولیه و همان unit
            if ep.section_head and all(r["id"] != ep.section_head_id for r in results):
                results.append({
                    "id": ep.section_head_id,
                    "name": ep.section_head.get_full_name() or ep.section_head.username,
                    "role_code": Settings.ROLE_SECTION_HEAD,
                })

    return JsonResponse({"results": results})

def employees_api(request):
    unit_code = request.GET.get("unit_id")
    if not unit_code:
        return JsonResponse({"results": []})

    qs = EmployeeProfile.objects.filter(
        unit__unit_code=unit_code,
        user__isnull=False
    ).select_related("user", "job_role")

    data = [{
        "id": emp.user_id,
        "name": str(emp),
        "role_code": emp.job_role.code if emp.job_role else ""
    } for emp in qs]

    return JsonResponse({"results": data})

def data_api(request):
    # TODO: دیتای واقعی چارت/پی، سال‌ها و ...
    fmt = request.GET.get("format")
    if fmt == "years":
        return JsonResponse({"years": []})
    return JsonResponse({
        "summary": {"unit": "", "employee": "", "count": 0, "avg": 0},
        "chart": {"title": "", "labels": [], "datasets": []},
        "pie": {"title": "", "labels": [], "data": []},
    })

@staff_member_required
def get_jobroles_api(request):
    raw = request.GET.get("unit_id")
    unit = _get_unit_by_id_or_code(raw)
    if not unit:
        return JsonResponse({"roles": [], "titles": []})

    # فقط جاب‌رول‌هایی که به این واحد وصل‌اند
    roles_qs = JobRole.objects.filter(
        allowed_units__id=unit.id
    ).distinct()

    roles = []
    for r in roles_qs:
        # اگر فیلد title وجود نداشت، مشکلی پیش نیاد
        name = getattr(r, "title", None) or getattr(r, "name", None) or str(r)
        roles.append({
            "id": r.id,
            "name": name,
        })

    # فعلاً titles رو مثل roles برمی‌گردونیم
    titles = list(roles)

    return JsonResponse({"roles": roles, "titles": titles})

@staff_member_required
def get_units_by_org(request):
    org_id = request.GET.get("org_id")
    if not org_id:
        return JsonResponse({"units": []})

    units = Unit.objects.filter(
        organization_id=org_id
    ).order_by("name")

    return JsonResponse({
        "units": [
            {"id": u.id, "name": u.name}
            for u in units
        ]
    })

@staff_member_required
def get_jobtitles_api(request):
    raw = request.GET.get("unit_id")
    unit = _get_unit_by_id_or_code(raw)
    if not unit:
        return JsonResponse({"titles": []})

    qs = JobTitle.objects.filter(unit=unit, is_active=True).order_by("name")

    return JsonResponse({
        "titles": [
            {"id": t.id, "name": t.name}
            for t in qs
        ]
    })


