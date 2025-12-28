# core/views/manager/evaluations.py
from datetime import date
from typing import Optional, List
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.db.models import Q
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from core.constants import Settings
from core.mixins.organization_scope import scope_queryset
from core.constants import WorkflowStatus
from core.approval.workflow_engine import WorkflowEngine
from core.models import EvaluationSignature

from core.models import (
    EmployeeProfile,
    EvaluationItem,
    FormTemplate,
    FormCriterion,
)
from core.models import Evaluation
from core.services.permissions import (
    default_form_for_employee,
    can_evaluate,
    RoleLevel,
)
from core.services.evaluation_access import (
    can_view_evaluation,
    can_edit_evaluation,
    can_approve_evaluation,
    is_hr,
    is_unit_manager,
    is_factory_manager,
)

def _back(request, default="/eval/dashboard/"):
    return redirect(request.META.get("HTTP_REFERER") or default)

@login_required
@require_http_methods(["GET"])
def ajax_managers_for_unit(request, unit_key: str):
    """
    unit_key می‌تواند ID عددی واحد (از ادمین) یا خود unit_code باشد.
    برای واحدهای خاص:
      - 219: لجستیک → مدیر مستقیم = مدیر کارخانه (role_code=900)
      - 208: تحقیق‌وتوسعه → مدیر مستقیم = مدیر کارخانه (role_code=900)
      - 100: مدیریت/کارخانه → مدیر مستقیم = مدیر کارخانه (role_code=900)
    سایر واحدها: 901 (مدیر واحد) و 902 (رئیس واحد)
    """
    from django.shortcuts import get_object_or_404
    from core.models import EmployeeProfile, Unit  # اگر اسم مدل Unit متفاوت است همین‌جا اصلاح کن

    # unit_code را قطعی کن
    if unit_key.isdigit():
        unit = get_object_or_404(Unit, id=int(unit_key))
        unit_code = str(unit.unit_code)
    else:
        unit_code = str(unit_key)

    # بررسی اینکه آیا واحد فعلی جزو واحدهای خاص مدیر کارخانه است
    if unit_code in (set(Settings.FACTORY_SPECIALIST_UNITS) | Settings.HEAD_UNIT_CODES):
        # مدیر کارخانه (role_code=900)
        qs = (
            EmployeeProfile.objects
            .select_related("user", "job_role", "unit")
            .filter(job_role__code=Settings.ROLE_FACTORY_MANAGER)
            .order_by("personnel_code")
        )
        data = [
            {
                "id": ep.id,
                "name": (ep.user.get_full_name() or ep.title or ep.personnel_code),
                "role_code": Settings.ROLE_FACTORY_MANAGER,
            }
            for ep in qs
        ]
        return JsonResponse({"results": data})

    # سایر واحدها: 901 و 902
    qs = (EmployeeProfile.objects
          .select_related("user", "job_role", "unit")
          .filter(unit__unit_code=unit_code,
                  job_role__code__in=[Settings.ROLE_UNIT_MANAGER,Settings.ROLE_SECTION_HEAD])
          .order_by("job_role__code", "personnel_code")
          )

    data = [{
        "id": ep.id,
        "name": (ep.user.get_full_name() or ep.title or ep.personnel_code),
        "role_code": ep.job_role.code,
    } for ep in qs]

    return JsonResponse({"results": data})

@login_required
@require_http_methods(["GET"])
def ajax_teams_for_manager(request, ep_id: int):
    ep = EmployeeProfile.objects.select_related("unit","job_role","user").filter(id=ep_id).first()
    if not ep:
        return JsonResponse({"results": []})
    team = (ep.team_code or "").strip()
    return JsonResponse({"results": [{"code": team, "label": team or "—"}]})

# ----------------------Helper----------------------
def _evaluator_profile(request):
    ep = (EmployeeProfile.objects
          .select_related("job_role", "unit")
          .filter(user=request.user).first())
    role = int(ep.job_role.code) if ep and ep.job_role and ep.job_role.code else None
    unit = ep.unit.unit_code if ep and ep.unit_id else ""
    team = (ep.team_code or "").strip() if ep and hasattr(ep, "team_code") else ""
    return role, unit, team, ep

def _period_for_months(months: int):
    """پایان = امروز، شروع = n ماه قبل؛ با روزِ ماه ثابت (اگر 31 نبود، خودش جمع‌وجور می‌شود)."""
    today = timezone.localdate()
    # «ماه قبل» بدون وابستگی به dateutil
    y, m = today.year, today.month
    m -= months
    while m <= 0:
        m += 12
        y -= 1
    # اگر روزِ ماه مقصد وجود نداشت، خودِ پایتون می‌اندازد به آخر ماه (ValueError را هندل می‌کنیم)
    d = min(today.day, 28)  # امن
    start = date(y, m, d)
    end = today
    return start, end

def _allowed_form_codes_for_evaluator(evaluator_role: int):
    """
    - 900 (مدیر کارخانه): فقط HR-F-84
    - 901 (مدیر): HR-F-84 + سایر فرم‌ها
    - 902 (رئیس): بدون HR-F-84
    - 903/907: فقط HR-F-80
    """
    if evaluator_role == RoleLevel.FACTORY_MANAGER:  # 900
        return [Settings.FORM_CODE_MANAGER, Settings.FORM_CODE_EXPERT, Settings.FORM_CODE_SUPERVISOR]
    if evaluator_role == RoleLevel.MANAGER:  # 901
        return [Settings.FORM_CODE_MANAGER, Settings.FORM_CODE_EMPLOYEE, Settings.FORM_CODE_TECHNICIAN, Settings.FORM_CODE_EXPERT, Settings.FORM_CODE_SUPERVISOR]
    if evaluator_role == RoleLevel.CHIEF:  # 902
        return [Settings.FORM_CODE_EMPLOYEE, Settings.FORM_CODE_TECHNICIAN, Settings.FORM_CODE_EXPERT, Settings.FORM_CODE_SUPERVISOR]
    if evaluator_role in (RoleLevel.SUPERVISOR, RoleLevel.SENIOR_SPEC):
        return [Settings.FORM_CODE_EMPLOYEE]
    return []

def _available_forms_for_user(unit_code: str, evaluator_role: int, allowed_codes: list[str]):
    """
    فقط فرم‌های Published را برمی‌گرداند که:
    1) طبق policy در allowed_codes مجازند، و
    2) در همان واحد، حداقل یک نفر با نقش‌های هدفِ فرم وجود دارد.
    """
    qs = FormTemplate.objects.filter(status="Published", code__in=allowed_codes).order_by("code")
    forms = []
    for f in qs:
        target_codes = list(f.applies_to_jobroles.values_list("code", flat=True))  # مثل ['906'] یا ['903','907']
        if not target_codes:
            continue
        if EmployeeProfile.objects.filter(
                unit__unit_code=unit_code,
                job_role__code__in=target_codes,
        ).exists():
            forms.append(f)
    return forms

@login_required
def forms_home_view(request):
    # اطلاعات نقش ارزیاب
    evaluator_role, evaluator_unit, evaluator_team, ep = _evaluator_profile(request)

    forms = []
    if evaluator_role is None:
        messages.error(request, "نقش ارزیاب (role_level) برای کاربر فعلی تنظیم نشده است.")
    else:
        allowed_codes = _allowed_form_codes_for_evaluator(evaluator_role)
        forms = list(
            FormTemplate.objects.filter(status="Published", code__in=allowed_codes)
            .order_by("code")
            .prefetch_related("criteria")
        )

    return render(request, "manager/evaluations/forms_home.html", {"forms": forms})

def _get_user_role_unit(user):
    """
    سعی می‌کنیم role_level و unit_code را از profile کاربر بخوانیم.
    اگر پروفایل نداشته باشد، None برمی‌گردانیم.
    """
    role = getattr(getattr(user, "profile", user), "role_level", None)
    unit = getattr(getattr(user, "profile", user), "unit_code", None)
    return role, (str(unit) if unit is not None else None)

def _subtract_months(d: date, months: int) -> date:
    # کم‌کردن n ماه از تاریخ به‌صورت امن (بدون dateutil)
    y = d.year
    m = d.month - months
    while m <= 0:
        m += 12
        y -= 1
    day = min(d.day, [31,
                      29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)

def _period_from_start_of_year(months: int, year: int = None, quarter: int = None):
    """
    تعیین بازه بر اساس سال و دوره (quarter):
    - اگر quarter داده نشود، به صورت پیش‌فرض دوره اول (ابتدای سال) است.
    """
    from datetime import date
    year = year or date.today().year

    if months == 3:
        q = quarter or 1
        start_month = (q - 1) * 3 + 1
        end_month = start_month + 2
        start_date = date(year, start_month, 1)
        end_day = 31 if end_month in (1, 3, 5, 7, 8, 10, 12) else (30 if end_month != 2 else 28)
        end_date = date(year, end_month, end_day)
        return start_date, end_date

    elif months == 6:
        q = quarter or 1
        start_month = (q - 1) * 6 + 1
        end_month = start_month + 5
        start_date = date(year, start_month, 1)
        end_day = 30 if end_month in (4, 6, 9, 11) else 31
        end_date = date(year, end_month, end_day)
        return start_date, end_date

    elif months == 9:
        return date(year, 1, 1), date(year, 9, 30)

    elif months == 12:
        return date(year, 1, 1), date(year, 12, 31)

    else:
        return date(year, 1, 1), date(year, 12, 31)

def _target_roles_for_form(form_code: str):
    """نقش‌های هدف هر فرم (نقش ارزیابی‌شونده‌ها)"""
    mapping = {
        Settings.FORM_CODE_EMPLOYEE: [RoleLevel.EMPLOYEE],  # 904
        Settings.FORM_CODE_TECHNICIAN: [RoleLevel.ASSOCIATE],  # 908
        Settings.FORM_CODE_SUPERVISOR: [RoleLevel.SUPERVISOR, RoleLevel.SENIOR_SPEC],  # 903, 907
        Settings.FORM_CODE_EXPERT: [RoleLevel.SPECIALIST],  # 906
        Settings.FORM_CODE_MANAGER: [RoleLevel.MANAGER, RoleLevel.CHIEF],  # 901, 902
    }
    return mapping.get(form_code, [])

def _team_people_scope(evaluator_role: int, evaluator_unit: str, ep):
    """
    محدوده‌ی افراد قابل مشاهده/ارزیابی بر اساس نقش ارزیاب.
    اگر بعداً فیلد team_code به EmployeeProfile اضافه کردی، می‌تونی اینجا هم ازش استفاده کنی.
    """
    # هیچ پروفایلی نداریم؟ خروجی تهی
    if not ep:
        return Q(pk__in=[])

    # مدیر: کلِ واحد خودش
    if evaluator_role == RoleLevel.MANAGER:
        return Q(unit__unit_code=evaluator_unit)

    # رئیس: فقط زیرمجموعه‌ی خودش در همان واحد
    if evaluator_role == RoleLevel.CHIEF:
        return Q(unit__unit_code=evaluator_unit) & (
                Q(section_head_id=ep.id) | Q(direct_supervisor_id=ep.id)
            # اگر team_code دارید:
            # | Q(team_code=getattr(ep, "team_code", ""))
        )

    # سرپرست/کارشناس مسئول: زیرمجموعه‌ی مستقیم خودش در واحد
    if evaluator_role in (RoleLevel.SUPERVISOR, RoleLevel.SENIOR_SPEC):
        return Q(unit__unit_code=evaluator_unit) & Q(direct_supervisor_id=ep.id)

    # سایر نقش‌ها: چیزی نمی‌بینند
    return Q(pk__in=[])

def _scoped_evaluations_queryset(selected_tpl, pstart, pend, evaluator_role: int, evaluator_unit: str, ep):
    """
    QuerySet پایه برای تب‌های Draft/Submitted/Approved با رعایت محدوده‌ها:
    - HR-F-84: فقط مدیر کارخانه (900) بدون محدودیت واحد می‌بیند؛ بقیه محدود به واحد خودشان.
    - سایر فرم‌ها: همیشه به واحد ارزیاب محدود؛ اگر ارزیاب «رئیس» است، به team_code خودش هم محدود.
    """
    from core.models import Evaluation  # محلی برای ایمنی

    ev_qs = (Evaluation.objects
             .select_related("template")
             .filter(template=selected_tpl,
                     template_version=selected_tpl.version,
                     period_start=pstart, period_end=pend))
    ev_qs = scope_queryset(ev_qs, user=ep.user)

    if selected_tpl.code == Settings.FORM_CODE_MANAGER:
        if evaluator_role != RoleLevel.FACTORY_MANAGER:
            ev_qs = ev_qs.filter(unit_code=evaluator_unit)
    else:
        ev_qs = ev_qs.filter(unit_code=evaluator_unit)
        if evaluator_role == RoleLevel.CHIEF:
            team = (getattr(ep, "team_code", "") or "").strip()
            if team:
                ev_qs = ev_qs.filter(team_code=team)

    return ev_qs.order_by("-updated_at")

def _eligible_employees_queryset_scoped(form_code: str, evaluator_role: int, evaluator_unit: str, ep):
    """
    افراد هدف برای تب «To-Do» با رعایت سیاست‌های نقش/واحد/تیم.
    - HR-F-84:
        * مدیر واحد (901) => فقط رؤسا (902) همان واحد
        * مدیر کارخانه (900) => مدیرها و رؤسا در همه واحدها
        * بقیه => هیچ‌کس
    - سایر فرم‌ها: نقش‌های هدف از خود Template + الزام هم‌واحدی
        * اگر ارزیاب «رئیس» است (902): فقط همان team_code (یا در نبود team_code، فقط زیردستانی که section_head = خودِ رئیس هستند)
    """
    from core.models import EmployeeProfile, FormTemplate  # محلی تا circular import نگیریم

    if form_code == Settings.FORM_CODE_MANAGER:
        if evaluator_role == RoleLevel.MANAGER:  # 901
            qs = (EmployeeProfile.objects
                  .select_related("user", "unit", "job_role")
                  .filter(job_role__code=Settings.ROLE_SECTION_HEAD,unit__unit_code=evaluator_unit))
        elif evaluator_role == RoleLevel.FACTORY_MANAGER:  # 900
            qs = (EmployeeProfile.objects
                  .select_related("user", "unit", "job_role")
                  .filter(job_role__code__in=[Settings.ROLE_UNIT_MANAGER,Settings.ROLE_SECTION_HEAD,]))
        else:
            qs = EmployeeProfile.objects.none()
        return qs

    # سایر فرم‌ها: از Template نقش‌های هدف را بخوان
    target_codes = list(
        FormTemplate.objects.filter(code=form_code, status="Published")
        .values_list("applies_to_jobroles__code", flat=True).distinct()
    )
    qs = (EmployeeProfile.objects
          .select_related("user", "unit", "job_role")
          .filter(job_role__code__in=target_codes, unit__unit_code=evaluator_unit))

    # اگر ارزیاب «رئیس» است، فقط تیم خودش را ببیند
    if evaluator_role == RoleLevel.CHIEF:
        team = (getattr(ep, "team_code", "") or "").strip()
        if team:
            qs = qs.filter(team_code=team)
        else:
            # فالبک: فقط کسانی که section_head = خودِ رئیس هستند
            qs = qs.filter(section_head=ep.user)

    return qs

def _pick_selected_template(forms: List[FormTemplate], form_code: Optional[str]) -> Optional[FormTemplate]:
    """
    از بین لیست «forms» (لیست، نه QuerySet) یک فرم را انتخاب کن.
    """
    if not forms:
        return None
    if form_code:
        found = next((f for f in forms if f.code == form_code), None)
        if found:
            return found
    return forms[0]

def attach_workflow_flags(evaluations, user):
    result = []
    for ev in evaluations:
        engine = WorkflowEngine(ev)
        result.append({
            "ev": ev,
            "can_approve": engine.can_approve(user),
            "current_step": engine.core.current_step(),
        })
    return result

# -------------dashboard-----------------
@login_required
@require_http_methods(["GET"])
def dashboard_view(request):
    # پروفایل ارزیاب
    evaluator_role, evaluator_unit, evaluator_team, ep = _evaluator_profile(request)
    # تعیین نقش گردش‌کار کاربر
    wf_role = None
    if ep:
        if ep.job_role.code == Settings.ROLE_FACTORY_MANAGER:
            wf_role = "factory_manager"
        elif ep.job_role.code == Settings.ROLE_UNIT_MANAGER or ep.job_role.code == Settings.ROLE_SECTION_HEAD or ep.job_role.code == Settings.ROLE_RESPONSIBLE:
            wf_role = "manager"
        elif ep.job_role.code == Settings.ROLE_HR:  # اگر در سیستم HR داری
            wf_role = "hr"

    if evaluator_role is None:
        messages.error(request, "نقش ارزیاب (role_level) برای کاربرِ فعلی تنظیم نشده است.")
        allowed_codes = []
    else:
        allowed_codes = _allowed_form_codes_for_evaluator(evaluator_role)

    # فرم‌های مجاز منتشرشده
    forms = list(FormTemplate.objects.filter(status="Published", code__in=allowed_codes).order_by("code"))

    # انتخاب‌های کاربر
    selected_code = request.GET.get("form_code") or (forms[0].code if forms else None)
    months = int(request.GET.get("months", "3"))
    today = date.today()
    pstart = _subtract_months(today, months)
    pend = today

    selected_tpl = next((f for f in forms if f.code == selected_code), None)
    if not selected_tpl:
        # هیچ فرمی مجاز نیست؛ صفحه خالی
        context = {
            "forms": forms, "selected_code": selected_code,
            "months": months, "month_choices": [3, 6, 9, 12],
            "period_start": pstart, "period_end": pend,
            "todo": [], "drafts": [], "submitted": [], "approved": [],
            "evaluator_role": evaluator_role, "evaluator_unit": evaluator_unit, "evaluator_team": evaluator_team,
        }
        return render(request, "manager/evaluations/dashboard.html", context)

    # ---- 1) people_qs (کسانی که می‌توانم برایشان ارزیابی بسازم) ----
    if selected_tpl.code == Settings.FORM_CODE_MANAGER:
        if evaluator_role == RoleLevel.MANAGER:  # 901
            # مدیر واحد: فقط رؤسا (902) همان واحد
            people_qs = (EmployeeProfile.objects
                         .select_related("user", "unit", "job_role")
                         .filter(job_role__code=Settings.ROLE_SECTION_HEAD, unit__unit_code=evaluator_unit)
                         .order_by("personnel_code"))
        elif evaluator_role == RoleLevel.FACTORY_MANAGER:  # 900
            # مدیر کارخانه: مدیرها و رؤسا بدون محدودیت واحد
            people_qs = (EmployeeProfile.objects
                         .select_related("user", "unit", "job_role")
                         .filter(job_role__code__in=[Settings.ROLE_UNIT_MANAGER, Settings.ROLE_SECTION_HEAD])
                         .order_by("personnel_code"))
        else:
            people_qs = EmployeeProfile.objects.none()
    #//////
    else:
        # HR-F-83 – کارشناسان لجستیک/R&D مخصوص مدیر کارخانه
        if selected_tpl.code == Settings.FORM_CODE_EXPERT and evaluator_role == RoleLevel.FACTORY_MANAGER:
            people_qs = (
                EmployeeProfile.objects
                .select_related("user", "unit", "job_role")
                .filter(
                    job_role__code=Settings.ROLE_EXPERT,
                    unit__unit_code__in=Settings.FACTORY_SPECIALIST_UNITS,
                )
            )
        # HR-F-82 – فقط مسئول دفتر برای مدیر کارخانه
        elif selected_tpl.code == Settings.FORM_CODE_SUPERVISOR and evaluator_role == RoleLevel.FACTORY_MANAGER:
            people_qs = (
                EmployeeProfile.objects
                .select_related("user", "unit", "job_role")
                .filter(job_role__code=Settings.ROLE_OFFICE_ASSISTANT)
            )
        # سایر نقش‌ها (برای مدیر واحد، رئیس، سرپرست…)
        else:
            target_codes = list(selected_tpl.applies_to_jobroles.values_list("code", flat=True))
            people_qs = (
                EmployeeProfile.objects
                .select_related("user", "unit", "job_role")
                .filter(
                    job_role__code__in=target_codes,
                    unit__unit_code=evaluator_unit  # این فقط برای مدیر واحد است
                )
            )

    # ---- 2) To-Do: حذف کسانی که در همین فرم/بازه ارزیابی‌شان ساخته شده ----
    done_qs = Evaluation.objects.filter(
        template=selected_tpl,
        template_version=selected_tpl.version,
        period_start=pstart,
        period_end=pend,
        is_archived=False,
    ).values_list("employee_id", flat=True)

    todo = list(people_qs.exclude(personnel_code__in=done_qs)[:200])

   # ===================== بخش‌های مستقل داشبورد ======================

    # Draft → 10 آخر
    drafts = list(
        Evaluation.objects.filter(
            evaluator=request.user,
            status=Evaluation.Status.DRAFT,
            is_archived=False
        ).order_by("-updated_at")[:10]
    )

    # Submitted → 5 آخر
    recent_submitted = list(
        Evaluation.objects.filter(
            evaluator=request.user,
            status=Evaluation.Status.SUBMITTED,
            is_archived=False
        ).order_by("-updated_at")[:5]
    )
    # Approved → 5 آخر
    approved = list(
        Evaluation.objects.filter(
            evaluator=request.user,
            status=WorkflowStatus.FINAL_APPROVED,
            is_archived=False
        ).order_by("-approved_at")[:5]
    )

    # Archived → 5 آخر (از active جداست)
    archived_recent = list(
        Evaluation.objects
        .filter(evaluator=request.user, is_archived=True)
        .order_by("-archived_at")[:5]
    )

    # منقضی‌ها → همون قبلی بهتره ولی limit بذاریم
    stale_drafts = list(
        Evaluation.objects.filter(
            evaluator=request.user,
            status=Evaluation.Status.EXPIRED,
            is_archived=False
        ).order_by("-updated_at")[:5]
    )
    submitted = recent_submitted

    #==================================================
    # ==================================================
    # --- counters for dashboard (Approval Workflow) ---
    # ==================================================
    # Draft (همان قبلی)
    count_draft = Evaluation.objects.filter(
        evaluator=request.user,
        status=Evaluation.Status.DRAFT,
        is_archived=False
    ).count()

    count_submitted = scope_queryset(
        Evaluation.objects.filter(
            status=Evaluation.Status.SUBMITTED,
            is_archived=False
        ),
        user=request.user
    ).count()

    # HR Review
    count_hr = Evaluation.objects.filter(
        status=WorkflowStatus.HR_REVIEW,
        is_archived=False
    ).count()

    # Manager Review
    count_manager = Evaluation.objects.filter(
        status=WorkflowStatus.MANAGER_REVIEW,
        is_archived=False
    ).count()

    # Factory Manager Review
    count_factory = Evaluation.objects.filter(
        status=WorkflowStatus.FACTORY_REVIEW,
        is_archived=False
    ).count()

    # Final Approved
    count_final = Evaluation.objects.filter(
        status=WorkflowStatus.FINAL_APPROVED,
        is_archived=False
    ).count()

    count_approved = Evaluation.objects.filter(
        evaluator=request.user,
        status=Evaluation.Status.APPROVED,
        is_archived=False
    ).count()

    # Rejected (هر سه حالت)
    count_rejected = Evaluation.objects.filter(
        status__in=[
            WorkflowStatus.HR_REJECTED,
            WorkflowStatus.MANAGER_REJECTED,
            WorkflowStatus.FACTORY_REJECTED,
        ],
        is_archived=False
    ).count()

    # Archived (بدون تغییر)
    count_archived = Evaluation.objects.filter(
        evaluator=request.user,
        is_archived=True
    ).count()

    # ==================================================
    # lists for dashboard cards
    # ==================================================
    hr = scope_queryset(
        Evaluation.objects.filter(
            status=WorkflowStatus.HR_REVIEW,
            is_archived=False,
        ),
        user=request.user
    )

    manager_qs = scope_queryset(
        Evaluation.objects.filter(
            status=WorkflowStatus.MANAGER_REVIEW,
            is_archived=False,
        ),
        user=request.user
    )

    manager = attach_workflow_flags(manager_qs, request.user)

    factory = scope_queryset(
        Evaluation.objects.filter(
            status=WorkflowStatus.FACTORY_REVIEW,
            is_archived=False,
        ),
        user=request.user
    )

    final = scope_queryset(
        Evaluation.objects.filter(
            status=WorkflowStatus.FINAL_APPROVED,
            is_archived=False,
        ),
        user=request.user
    )

    rejected = scope_queryset(
        Evaluation.objects.filter(
            status__in=[
                WorkflowStatus.HR_REJECTED,
                WorkflowStatus.MANAGER_REJECTED,
                WorkflowStatus.FACTORY_REJECTED,
            ],
            is_archived=False,
        ),
        user=request.user
    )

    hr_pending_count = Evaluation.objects.filter(
        is_archived=False,
        status=Evaluation.Status.SUBMITTED,
    ).exclude(
        signatures__role="hr",
        signatures__signed_at__isnull=False,
    ).distinct().count()

    factory_pending_count = Evaluation.objects.filter(
        is_archived=False,
        status=Evaluation.Status.FACTORY_REVIEW,
    ).exclude(
        signatures__role="factory",
        signatures__signed_at__isnull=False,
    ).distinct().count()

    # فیلتر کردن لیست‌ها بر اساس نقش گردش‌کار
    if wf_role == "hr":
        manager = None
        factory = None
    elif wf_role == "manager":
        hr = None
        factory = None
    elif wf_role == "factory_manager":
        hr = None
        manager = None

    # ==================================================
    # Context
    # ==================================================

    context = {
        "forms": forms,
        "selected_code": selected_code,
        "months": months,
        "month_choices": [3, 6, 9, 12],
        "period_start": pstart,
        "period_end": pend,
        "todo": todo,
        "drafts": drafts,
        "archived_recent": archived_recent,

        # Evaluator info
        "evaluator_role": evaluator_role,
        "evaluator_unit": evaluator_unit,
        "evaluator_team": evaluator_team,
        "approved" : approved,
        "count_approved" :count_approved,
        "submitted": submitted,

        # recent activity
        "recent_submitted": recent_submitted,
        "stale_drafts": stale_drafts,
        "now": timezone.now(),

        # COUNTERS
        "count_draft": count_draft,
        "count_hr": count_hr,
        "count_manager": count_manager,
        "count_factory": count_factory,
        "count_final": count_final,
        "count_rejected": count_rejected,
        "count_archived": count_archived,
        "count_submitted": count_submitted,
        "hr_pending_count":hr_pending_count,
        "factory_pending_count": factory_pending_count,
        "hr": hr,
        "manager": manager,
        "factory": factory,
        "final": final,
        "rejected": rejected,
        "wf_role": wf_role,
    }
    context["is_hr"] = is_hr(request.user)
    context["is_manager"] = is_unit_manager(request.user)
    context["is_factory_manager"] = is_factory_manager(request.user)

    return render(request, "manager/evaluations/dashboard.html", context)

# -------------List (per-status)-----------------
@login_required
@require_http_methods(["POST"])
def create_evaluation_view(request):
    """
    ساخت/دریافت ارزیابی برای یک کارمند از داشبورد، سپس هدایت به صفحه ویرایش.
    """
    form_code = request.POST.get("form_code")
    employee_id = request.POST.get("employee_id")
    months = int(request.POST.get("months", "3"))

    if not (form_code and employee_id):
        return HttpResponseBadRequest("پارامترهای لازم موجود نیست.")

    try:
        tmpl = FormTemplate.objects.get(code=form_code, status="Published")
    except FormTemplate.DoesNotExist:
        return HttpResponseBadRequest("فرم منتشرشده پیدا نشد.")

    # پروفایل ارزیاب
    evaluator_role, evaluator_unit, evaluator_team, ep = _evaluator_profile(request)

    # اطلاعات کارمند
    emp = EmployeeProfile.objects.select_related("job_role", "unit") \
        .filter(personnel_code=employee_id).first()
    # TODO: اگر فیلد شناسه متفاوت است، اینجا اصلاح کن
    if not emp:
        return HttpResponseBadRequest("پرسنل موردنظر پیدا نشد.")

    # چک مجوز با همان سرویسی که ساختیم
    employee_role = int(emp.job_role.code) if emp.job_role and emp.job_role.code else None
    employee_unit = emp.unit.unit_code if emp.unit else ""
    employee_name = (getattr(emp, "user", None) and (emp.user.get_full_name() or emp.user.username)) \
                    or getattr(emp, "title", None) \
                    or emp.personnel_code

    if not can_evaluate(
            evaluator_role=evaluator_role,
            employee_role=employee_role,
            form_code=form_code,
            evaluator_unit=evaluator_unit,
            employee_unit=employee_unit,
            require_same_unit=True,  # HR-F-84 به‌طور خودکار داخل can_evaluate استثناء شده
    ):
        return HttpResponseForbidden("شما مجاز به ارزیابی این پرسنل با این فرم نیستید.")

    # بازه
    pstart, pend = _period_from_start_of_year(months)

    # ساخت/دریافت ارزیابی (کلید یکتا: employee_id + template/version + period)
    ev, created = Evaluation.objects.get_or_create(
        template=tmpl,
        template_version=tmpl.version,
        employee_id=str(employee_id),
        period_start=pstart,
        period_end=pend,
        defaults={
            "status": Evaluation.Status.DRAFT,
            "employee_name": employee_name,
            "unit_code": employee_unit,
            "role_level": employee_role,
            # "team_code": getattr(emp, "team_code", ""),
            "evaluator": request.user,
            "manager_id": str(request.user.id),
            "manager_name": request.user.get_full_name() or request.user.username,
            # کپی فلگ‌ها از Template
            "show_employee_signature": tmpl.show_employee_signature,
            "show_manager_signature": tmpl.show_manager_signature,
            "show_hr_signature": tmpl.show_hr_signature,
            "show_employee_comment": tmpl.show_employee_comment,
            "show_next_period_goals": tmpl.show_next_period_goals,
        }
    )

    # اگر تازه ساخته شده، آیتم‌ها را تزریق کن
    if created and ev.items.count() == 0:
        for c in tmpl.criteria.all():
            EvaluationItem.objects.create(
                evaluation=ev, criterion=c,
                criterion_order=c.order, criterion_title=c.title, weight=c.weight,
            )
    # --- ست کردن Draft/Expiration ---
    if created:
        ev.draft_started = True
        ev.save()  # اول ذخیره تا created_at پر بشه
        ev.ensure_visible_until()
        ev.save(update_fields=["visible_until", "draft_started", "updated_at"])
    elif not ev.visible_until:
        # اگر قبلاً ساخته شده ولی تاریخ دیده شدن ندارد
        ev.ensure_visible_until()
        ev.save(update_fields=["visible_until", "updated_at"])

    messages.success(request, f"ارزیابی {'ساخته' if created else 'دریافت'} شد.")
    return redirect("eval_edit", pk=ev.id)

# ------------ویوی لیست:-----------------

@login_required
@require_http_methods(["GET"])
def evaluation_list_view(request, status: str):
    # 1) فرم انتخاب‌شده و بازه
    months = int(request.GET.get("months") or 3)
    form_code = request.GET.get("form_code")

    # نقش/واحد/تیم ارزیاب
    ep = getattr(request.user, "employeeprofile", None)
    if not ep or not ep.job_role_id:
        messages.error(request, "نقش ارزیاب برای کاربر فعلی تنظیم نشده است.")
        return redirect("eval_dashboard")

    role_code = ep.job_role.code
    unit_code = ep.unit.unit_code if ep.unit_id else ""
    rl = int(role_code) if role_code and role_code.isdigit() else None

    # اگر فرم انتخاب نشده بود: فرم پیش‌فرض نقش
    if not form_code and rl:
        form_code = default_form_for_employee(rl)

    # فقط فرم‌های مجاز این ارزیاب
    allowed_codes = []
    for code in [Settings.FORM_CODE_EMPLOYEE,Settings.FORM_CODE_TECHNICIAN,
                 Settings.FORM_CODE_SUPERVISOR, Settings.FORM_CODE_EXPERT,
                 Settings.FORM_CODE_MANAGER,]:
        if can_evaluate(evaluator_role=rl, employee_role=rl, form_code=code, evaluator_unit=unit_code,
                        employee_unit=unit_code, require_same_unit=False):
            allowed_codes.append(code)

    forms = _available_forms_for_user(unit_code, rl, allowed_codes)

    # فرم انتخابی
    selected_tpl = None
    if form_code:
        selected_tpl = next((f for f in forms if f.code == form_code), None)
    if not selected_tpl and forms:
        selected_tpl = forms[0]

    if not selected_tpl:
        messages.error(request, "فرمی برای نقش شما یافت نشد.")
        return redirect("eval_dashboard")

    form_code = selected_tpl.code

    # form_code = selected_tpl.code if selected_tpl else None
    pstart, pend = _period_for_months(months)

    # 2) داده‌ها
    page_title = ""
    rows = []
    is_todo = (status.lower() == "todo")
    if is_todo:
        people_qs = _eligible_employees_queryset_scoped(selected_tpl.code, rl, unit_code, ep)
        done_ids = Evaluation.objects.filter(
            template__code=form_code,
            template_version=selected_tpl.version,
            period_start=pstart, period_end=pend
        ).values_list("employee_id", flat=True)
        people_qs = people_qs.exclude(personnel_code__in=done_ids)

        paginator = Paginator(people_qs.order_by("personnel_code"), 25)
        page = paginator.get_page(request.GET.get("page"))
        rows = page
        page_title = "To-Do"
    else:
        ev_qs = _scoped_evaluations_queryset(selected_tpl, pstart, pend, rl, unit_code, ep)

        status_map = {
            "draft": Evaluation.Status.DRAFT,
            # مراحل جدید گردش‌کار
            "hr": WorkflowStatus.HR_REVIEW,
            "manager": WorkflowStatus.MANAGER_REVIEW,
            "factory": WorkflowStatus.FACTORY_REVIEW,
            # پایان گردش‌کار
            "approved": WorkflowStatus.FINAL_APPROVED,
            # برگشتی‌ها
            "rejected": [
                WorkflowStatus.HR_REJECTED,
                WorkflowStatus.MANAGER_REJECTED,
                WorkflowStatus.FACTORY_REJECTED,
            ],
        }
        st = status_map.get(status.lower(), Evaluation.Status.DRAFT)
        ev_qs = scope_queryset(ev_qs, user=request.user)

        # -----------------------------------------
        # Draft
        # -----------------------------------------
        if st == Evaluation.Status.DRAFT:
            ev_qs = ev_qs.filter(
                status=Evaluation.Status.DRAFT,
                evaluator=request.user,
                visible_until__gte=timezone.now(),
                is_archived=False,
            )
            page_title = "In-Progress (Draft)"

        # -----------------------------------------
        # HR Review
        # -----------------------------------------
        elif st == WorkflowStatus.HR_REVIEW:
            ev_qs = ev_qs.filter(status=WorkflowStatus.HR_REVIEW)
            page_title = "در انتظار بررسی HR"

        # -----------------------------------------
        # Manager Review
        # -----------------------------------------
        elif st == WorkflowStatus.MANAGER_REVIEW:
            ev_qs = ev_qs.filter(status=WorkflowStatus.MANAGER_REVIEW)
            page_title = "در انتظار مدیر واحد"

        # -----------------------------------------
        # Factory Manager Review
        # -----------------------------------------
        elif st == WorkflowStatus.FACTORY_REVIEW:
            ev_qs = ev_qs.filter(status=WorkflowStatus.FACTORY_REVIEW)
            page_title = "در انتظار مدیر کارخانه"

        # -----------------------------------------
        # Final Approved
        # -----------------------------------------
        elif st == WorkflowStatus.FINAL_APPROVED:
            ev_qs = ev_qs.filter(status=WorkflowStatus.FINAL_APPROVED)
            page_title = "تأیید نهایی"

        # -----------------------------------------
        # Rejected (all rejection statuses)
        # -----------------------------------------
        elif isinstance(st, list):
            ev_qs = ev_qs.filter(status__in=st)
            page_title = "بازگشتی‌ها"

        paginator = Paginator(ev_qs, 25)
        page = paginator.get_page(request.GET.get("page"))
        rows = page

    ctx = {
        "forms": forms,
        "selected_code": form_code,
        "months": months,
        "month_choices": [3, 6, 9, 12],
        "period_start": pstart,
        "period_end": pend,
        "page_title": page_title,
        "rows": rows,
        "is_todo": is_todo,
        "status": status.lower(),
    }
    return render(request, "manager/evaluations/list.html", ctx)

# ---------- Start / Edit / Submit / Approve /  Save /----------

@login_required
@require_http_methods(["POST"])
def start_evaluation_view(request):
    rl, unit_code, team_code, ep = _evaluator_profile(request)
    if not rl:
        messages.error(request, "پروفایل ارزیاب ناقص است.")
        return redirect("eval_dashboard")

    form_code = request.POST.get("form_code")
    months = int(request.POST.get("months") or 3)
    employee_id = request.POST.get("employee_id")

    # 👇 اسکوپ سازمانی بر اساس پروفایل ارزیاب
    holding_id = ep.holding_id if hasattr(ep, "holding_id") else None
    factory_id = ep.factory_id if hasattr(ep, "factory_id") else None
    department_group_id = ep.department_group_id if hasattr(ep, "department_group_id") else None

    if not (form_code and employee_id):
        messages.error(request, "اطلاعات ناقص است.")
        return redirect("eval_dashboard")

    tpl = get_object_or_404(FormTemplate, code=form_code, status="Published")
    pstart, pend = _period_from_start_of_year(months)

    # جلوگیری از فرم تکراری در همان دوره (غیر Draft)
    existing = Evaluation.objects.filter(
        template=tpl,
        template_version=tpl.version,
        employee_id=str(employee_id),
        period_start=pstart,
        period_end=pend,
        is_archived=False,
    ).exclude(status=Evaluation.Status.DRAFT).first()

    if existing:
        messages.info(
            request,
            f"فرم ارزیابی این کارمند با وضعیت «{existing.get_status_display()}» قبلاً ایجاد شده است."
        )
        return redirect("eval_edit", pk=existing.pk)

    from django.utils import timezone

    with transaction.atomic():
        # 1) Draft فعال قبلی
        active = Evaluation.objects.filter(
            template=tpl,
            template_version=tpl.version,
            employee_id=str(employee_id),
            period_start=pstart,
            period_end=pend,
            status=Evaluation.Status.DRAFT,
            is_archived=False,
            evaluator_id=request.user.id,
            visible_until__gte=timezone.now(),
        ).first()

        if active:
            ev = active
            created = False

            update_fields = []

            # اگر Evaluator خالی بود
            if ev.evaluator_id is None:
                ev.evaluator = request.user
                ev.manager_id = str(ep.personnel_code) if ep else (ev.manager_id or "")
                ev.manager_name = request.user.get_full_name() or request.user.username
                update_fields += ["evaluator", "manager_id", "manager_name"]

            # 👇 اینجا مهمه: اگر قبلاً بدون اسکوپ ساخته شده، الان پرش کن
            if not ev.holding_id and holding_id:
                ev.holding_id = holding_id
                update_fields.append("holding_id")

            # if not ev.factory_id and factory_id:
            #     ev.factory_id = factory_id
            #     update_fields.append("factory_id")
            #
            # if not ev.department_group_id and department_group_id:
            #     ev.department_group_id = department_group_id
            #     update_fields.append("department_group_id")

            # (اختیاری) اگر واحد/تیم خالی باشند هم می‌تونی پر کنی:
            if not ev.unit_code and unit_code:
                ev.unit_code = unit_code
                update_fields.append("unit_code")

            if not ev.team_code and team_code:
                ev.team_code = team_code
                update_fields.append("team_code")

            if update_fields:
                ev.updated_at = timezone.now()
                update_fields.append("updated_at")
                ev.save(update_fields=update_fields)

        else:
            # 2) Draftهای منقضی‌شده همین کلیدها را آرشیو کن
            stale_qs = Evaluation.objects.filter(
                template=tpl,
                template_version=tpl.version,
                employee_id=str(employee_id),
                period_start=pstart,
                period_end=pend,
                status=Evaluation.Status.DRAFT,
                is_archived=False,
                visible_until__lt=timezone.now(),
            )
            for e in stale_qs:
                e.archive_if_expired()

            # 3) Draft تازه بساز (اینجا که خودت قبلاً درستش کردی 👇)
            ev = Evaluation.objects.create(
                template=tpl,
                template_version=tpl.version,
                status=Evaluation.Status.DRAFT,
                employee_id=str(employee_id),
                employee_name=_employee_display_name(employee_id),
                unit_code=unit_code,
                role_level=rl,
                team_code=team_code,
                evaluator=request.user,
                manager_id=str(ep.personnel_code) if ep else "",
                manager_name=request.user.get_full_name() or request.user.username,

                # 🌟 اسکوپ سازمانی
                holding_id=holding_id,
                # factory_id=factory_id,
                # department_group_id=department_group_id,

                show_employee_signature=tpl.show_employee_signature,
                show_manager_signature=tpl.show_manager_signature,
                show_hr_signature=tpl.show_hr_signature,
                show_employee_comment=tpl.show_employee_comment,
                show_next_period_goals=tpl.show_next_period_goals,
                period_start=pstart,
                period_end=pend,
            )
            created = True

            # 4) آیتم‌ها
            criteria_qs = FormCriterion.objects.filter(template_id=tpl.id).order_by("order", "id")
            if not criteria_qs.exists():
                messages.error(request, f"برای فرم {tpl.code} هیچ معیاری پیدا نشد.")
                ev.delete()
                return redirect("eval_dashboard")

            idx = 0
            for c in criteria_qs:
                idx += 1
                EvaluationItem.objects.create(
                    evaluation=ev,
                    criterion=c,
                    criterion_title=getattr(c, "title", "") or getattr(c, "name", "") or "",
                    weight=(getattr(c, "weight", None) or 1),
                    criterion_order=(getattr(c, "order", None) or idx),
                )

            # 5) مهلت Draft
            ev.draft_started = True
            ev.ensure_visible_until()
            ev.save(update_fields=["draft_started", "visible_until", "updated_at"])

    return redirect("eval_edit", pk=ev.id)

def _employee_display_name(personnel_code: str) -> str:
    ep = EmployeeProfile.objects.select_related("user").filter(personnel_code=personnel_code).first()
    if not ep:
        return str(personnel_code)
    return ep.user.get_full_name() or ep.title or str(personnel_code)

@login_required
@require_http_methods(["GET", "POST"])
def edit_evaluation_view(request, pk: int):
    # دریافت ارزیابی و قالب
    ev = get_object_or_404(
        Evaluation.objects.select_related("template"),
        pk=pk
    )
    # TEMP FIX: normalize legacy numeric status
    if isinstance(ev.status, int):
        ev.status = Evaluation.Status.DRAFT
        ev.save(update_fields=["status"])

    # پروفایل ارزیاب فعلی
    evaluator_role, evaluator_unit, evaluator_team, ep = _evaluator_profile(request)

    # ----------- مجوز مشاهده -----------
    engine = WorkflowEngine(ev)

    # مدیر HR = مدیر واحد (901) در واحد HR (202)
    is_hr_manager = (
            ep
            and ep.unit
            and ep.job_role
            and ep.unit.unit_code in Settings.HR_UNIT_CODES
            and ep.job_role.code == Settings.ROLE_UNIT_MANAGER
    )

    # مدیر کارخانه
    is_factory_manager = (
            ep
            and ep.job_role
            and ep.job_role.code == Settings.ROLE_FACTORY_MANAGER
    )

    can_view = (
            ev.evaluator_id == request.user.id  # مدیر ارزیاب
            or request.user.is_superuser  # سوپریوزر
            or is_hr_manager  # فقط مدیر HR
            or is_factory_manager  # مدیر کارخانه
    )

    if not can_view:
        return HttpResponseForbidden("مجوز مشاهده این ارزیابی را ندارید.")

    # ----------- مجوز ویرایش (فقط مدیران) -----------
    can_edit = (
            ev.status == Evaluation.Status.DRAFT
            and request.user == ev.evaluator
            and ep
            and ep.job_role.code in [
                Settings.ROLE_UNIT_MANAGER,  # مدیر واحد
                Settings.ROLE_SECTION_HEAD,  # رئیس
                Settings.ROLE_FACTORY_MANAGER,  # مدیر کارخانه
            ]
    )

    read_only = not can_edit

    # ==========================================================
    #                           POST
    # ==========================================================
    if request.method == "POST":
        # ------------------- ذخیره معمولی (فقط در Draft) -------------------
        if 'save' in request.POST or 'save_draft' in request.POST or 'save_submit' in request.POST:
            if not can_edit:
                return HttpResponseForbidden("امکان ویرایش این ارزیابی برای شما وجود ندارد.")

        # ------------------- ذخیره انتخاب گزینه‌ها -------------------
        items = list(ev.items.select_related("criterion"))
        for it in items:
            field = f"item_{it.id}"
            opt_id = request.POST.get(field)

            if not opt_id:
                continue  # ❗️دیگه پاک نکن

            opt = it.criterion.options.filter(id=opt_id).first()
            if opt:
                it.selected_option = opt
                it.selected_value = opt.value
                it.save(update_fields=["selected_option", "selected_value"])

        ev.recalc_scores()
        ev.updated_at = timezone.now()
        ev.save(update_fields=["updated_at"])

        # ------------------- ذخیره در Draft -------------------
        if 'save_draft' in request.POST:
            if not can_edit:
                return HttpResponseForbidden("امکان ذخیره پیش‌نویس ندارید.")

            # آیتم‌ها قبلاً ذخیره شده‌اند
            ev.status = Evaluation.Status.DRAFT
            ev.updated_at = timezone.now()
            ev.save(update_fields=["status", "updated_at"])

            messages.success(request, "فرم به‌صورت پیش‌نویس ذخیره شد.")
            return redirect("eval_dashboard")

        # ----------------------------- آرشیو -----------------------------
        if 'archive' in request.POST:
            if ev.status != Evaluation.Status.DRAFT:
                messages.error(request, "فقط فرم‌های پیش‌نویس قابل آرشیو هستند.")
                return redirect("eval_dashboard")

            if ev.evaluator_id != request.user.id and not request.user.is_superuser:
                return HttpResponseForbidden("اجازه آرشیو این ارزیابی را ندارید.")

            ev.is_archived = True
            ev.save(update_fields=["is_archived"])
            messages.success(request, "فرم با موفقیت آرشیو شد.")
            return redirect("eval_dashboard")
        # ----------------------------- ذخیره و ارسال -----------------------------
        if 'save_submit' in request.POST:

            # فقط ارزیاب اصلی یا سوپریوزر
            if request.user != ev.evaluator and not request.user.is_superuser:
                return HttpResponseForbidden("اجازه ارسال این ارزیابی را ندارید.")

            # فقط از Draft می‌شود ارسال کرد
            if ev.status != Evaluation.Status.DRAFT:
                messages.error(request, "این فرم قبلاً ارسال شده است.")
                return redirect("eval_dashboard")

            # ذخیره آیتم‌ها (همونی که داری)
            items = list(ev.items.select_related("criterion"))
            for it in items:
                field = f"item_{it.id}"
                opt_id = request.POST.get(field)
                if opt_id:
                    opt = it.criterion.options.filter(id=opt_id).first()
                    if opt:
                        it.selected_option = opt
                        it.selected_value = opt.value
                        it.save(update_fields=["selected_option", "selected_value"])

            ev.recalc_scores()

            # 👇👇👇 خط نجات
            ev.status = Evaluation.Status.SUBMITTED
            ev.updated_at = timezone.now()
            ev.save(update_fields=["status", "updated_at"])

            messages.success(request, "فرم با موفقیت ارسال شد.")
            return redirect("eval_dashboard")

        # ----------------------------- تأیید نهایی -----------------------------
        if 'approve' in request.POST:
            try:
                engine = WorkflowEngine(ev)

                if not engine.can_user_approve(request.user):
                    messages.error(request, "شما مجاز به تأیید این مرحله نیستید.")
                    return redirect("eval_dashboard")

                new_status = engine.approve(request.user)
                messages.success(request, f"فرم با موفقیت تأیید شد و به مرحله بعد رفت ({new_status}).")

            except Exception as ex:
                messages.error(request, f"خطا در تأیید: {ex}")

            return redirect("eval_dashboard")

        # ----------------------------- برگشت برای اصلاح -----------------------------
        if 'return' in request.POST:
            try:
                engine = WorkflowEngine(ev)

                new_status = engine.return_for_edit(request.user)
                if not new_status:
                    messages.error(request, "شما مجاز به بازگرداندن این مرحله نیستید.")
                    return redirect("eval_dashboard")

                messages.success(
                    request,
                    f"فرم با موفقیت برای اصلاح بازگردانده شد. وضعیت جدید: {new_status}"
                )

            except Exception as ex:
                messages.error(request, f"خطا در بازگرداندن: {ex}")

            return redirect("eval_dashboard")

    # ==========================================================
    #                           GET
    # ==========================================================
    items = (
        ev.items
        .select_related("criterion")
        .prefetch_related("criterion__options")
        .order_by("criterion_order", "id")
    )
    signatures = (
        EvaluationSignature.objects
        .filter(evaluation=ev)
        .select_related("evaluator")
        .order_by("signed_at")
    )

    # عنوان فرم
    if ev.template.code == "HR-F-84":
        if evaluator_role == RoleLevel.MANAGER:
            eval_title = "فرم ارزیابی رئیس"
        elif evaluator_role == RoleLevel.FACTORY_MANAGER:
            eval_title = (
                "فرم ارزیابی مدیر"
                if ev.role_level == RoleLevel.MANAGER
                else "فرم ارزیابی رئیس"
            )
        else:
            eval_title = ev.template.name or ev.template.code
    else:
        eval_title = ev.template.name or ev.template.code
    return render(
        request,
        "manager/evaluations/edit.html",
        {
            "ev": ev,
            "items": items,
            "read_only": read_only,
            "eval_title": eval_title,
            # برای تمپلیت
            "Evaluation": Evaluation,
            "WorkflowStatus": WorkflowStatus,
            "can_edit": can_edit,
            #"can_approve": can_approve_evaluation(request.user, ev),
            "can_approve":  engine.can_user_approve(request.user),
            "signatures": signatures,
        }
    )

@login_required
@require_http_methods(["POST"])
def evaluation_save_progress(request, pk: int):
    ev = get_object_or_404(Evaluation, pk=pk, status=Evaluation.Status.DRAFT)

    # فقط ارزیابِ همین Draft اجازه دارد
    if ev.evaluator_id != request.user.id:
        return HttpResponseForbidden("مجوز این عمل را ندارید.")

    # ذخیرهٔ انتخاب‌های فعلی (اگر چیزی زده شده باشد)
    items = list(ev.items.select_related("criterion").all())
    for it in items:
        field_name = f"item_{it.id}"
        opt_id = request.POST.get(field_name)
        if not opt_id:
            continue
        try:
            opt = it.criterion.options.get(id=int(opt_id))
            it.selected_option = opt
            it.selected_value = opt.value
            it.save(update_fields=["selected_option", "selected_value"])
        except Exception:
            continue

    # Draft را معتبر نگه دار
    ev.updated_at = timezone.now()
    if not ev.visible_until:
        ev.ensure_visible_until()
    ev.save(update_fields=["updated_at", "visible_until"])

    messages.info(request, "فرم شما ذخیره موقت شد و می‌توانید بعداً ادامه دهید.")
    return redirect("eval_dashboard")

@login_required
@require_http_methods(["POST"])
def bulk_archive_drafts_view(request):
    ids = request.POST.getlist("ids")
    if not ids:
        messages.info(request, "موردی انتخاب نشده است.")
        return redirect("eval_dashboard")

    qs = Evaluation.objects.filter(id__in=ids, status=Evaluation.Status.DRAFT)
    # فقط ارزیاب خودش بتواند آرشیو کند؛ مدیر/سوپریوزر همه را
    if not request.user.is_superuser:
        qs = qs.filter(evaluator=request.user)

    count = qs.update(is_archived=True)
    messages.success(request, f"{count} پیش‌نویس آرشیو شد.")
    return redirect("eval_dashboard")

@login_required
@require_http_methods(["POST"])
def bulk_delete_drafts_view(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("فقط سوپریوزر.")

    ids = request.POST.getlist("ids")
    if not ids:
        messages.info(request, "موردی انتخاب نشده است.")
        return redirect("eval_dashboard")

    qs = Evaluation.objects.filter(id__in=ids, status=Evaluation.Status.DRAFT)
    count = qs.delete()[0]
    messages.success(request, f"{count} پیش‌نویس به‌صورت دائم حذف شد.")
    return redirect("eval_dashboard")

@login_required
@require_http_methods(["POST"])
def archive_evaluation_view(request, pk: int):
    ev = get_object_or_404(Evaluation, pk=pk, status=Evaluation.Status.DRAFT)
    # فقط صاحب Draft یا سوپریوزر
    if not request.user.is_superuser and ev.evaluator_id != request.user.id:
        return HttpResponseForbidden("مجوز این عمل را ندارید.")
    ev.is_archived = True
    ev.save(update_fields=["is_archived"])
    messages.success(request, "پیش‌نویس آرشیو شد.")
    return redirect("eval_dashboard")

@login_required
@require_POST
def bulk_archive_drafts_view(request):
    print("📦 POST keys:", list(request.POST.keys()))
    print("🧩 ids list:", request.POST.getlist("ids"))
    ids = request.POST.getlist("ids")  # ← با name="ids" در فرم هماهنگ است
    if not ids:
        messages.warning(request, "هیچ موردی انتخاب نشده است.")
        return redirect(request.META.get("HTTP_REFERER", "/eval/dashboard/"))

    now = timezone.now()

    # فقط موارد انتخاب‌شده که هنوز آرشیوشده نیستند
    qs = Evaluation.objects.filter(id__in=ids, is_archived=False)

    # فقط منقضی‌ها یا درفت‌هایی که مهلت‌شان گذشته
    qs = qs.filter(
        Q(status=Evaluation.Status.EXPIRED) |
        Q(status=Evaluation.Status.DRAFT, visible_until__lt=now)
    )

    # اختیار: محدودیت دسترسی (ارزیاب فقط مال خودش، مگر HR/ادمین)
    if not (request.user.is_staff or request.user.is_superuser):
        qs = qs.filter(evaluator=request.user)

    count = qs.count()
    if count == 0:
        messages.info(request, "هیچ فرم قابل آرشیو یافت نشد.")
        return redirect(request.META.get("HTTP_REFERER", "/eval/dashboard/"))

    qs.update(is_archived=True, updated_at=timezone.now())
    messages.success(request, f"{count} فرم با موفقیت آرشیو شد.")
    return redirect(request.META.get("HTTP_REFERER", "/eval/dashboard/"))

@login_required
@require_POST
def eval_approve(request, pk: int):
    ev = get_object_or_404(Evaluation, pk=pk)

    # جلوگیری از مشاهده غیرمجاز
    if not can_view_evaluation(request.user, ev):
        return HttpResponseForbidden("اجازه مشاهده این فرم را ندارید.")

    # جلوگیری از تأیید غیرمجاز
    if not can_approve_evaluation(request.user, ev):
        return HttpResponseForbidden("اجازه تأیید این فرم را ندارید.")

    # اجرای گردش کار (رفتن به مرحله بعد)
    ev.advance_workflow(request.user)

    messages.success(request, "فرم با موفقیت به مرحله بعد منتقل شد.")
    return redirect("eval_dashboard")

@login_required
@require_POST
def eval_reject(request, pk: int):
    ev = get_object_or_404(Evaluation, pk=pk)

    if not can_view_evaluation(request.user, ev):
        return HttpResponseForbidden("اجازه مشاهده این فرم را ندارید.")

    if not can_approve_evaluation(request.user, ev):
        return HttpResponseForbidden("اجازه بازگرداندن این فرم را ندارید.")

    # برگشت به DRAFT طبق Workflow جدید
    ev.reject_workflow(request.user)

    messages.warning(request, "فرم برای اصلاح به مرحله پیش‌نویس بازگردانده شد.")
    return redirect("eval_dashboard")



