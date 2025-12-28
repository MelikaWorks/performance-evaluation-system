# manager/reports.py
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from core.models import Evaluation
from core.models import FormTemplate
from core.models import EmployeeProfile, Unit
from core.constants import Settings
from django.db.models import Q

def is_factory_manager(user):
    ep = getattr(user, "employee_profile", None)
    if not ep or not ep.job_role:
        return False

    return ep.job_role.code == Settings.ROLE_FACTORY_MANAGER

# ---- helpers ----
def _digits_en(s: str) -> str:
    return str(s).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))

def _int_safe(val, default=None):
    try:
        return int(_digits_en(val))
    except Exception:
        return default

@login_required
def reports_dashboard_view(request):
    """
    گزارش ارزیابی برای مدیران:
    - مدیر کارخانه: انتخاب واحد → پرسنل → گزارش
    - مدیر واحد: فقط پرسنل واحد خودش
    - فیلتر بر اساس سال و بازه (۳/۶/۹/۱۲ یا کل سال)
    """
    from django.db.models import Avg, FloatField, Case, When, F
    from django.db.models.functions import Coalesce
    from django.utils.safestring import mark_safe
    from django.db.models import ExpressionWrapper, fields
    from datetime import date
    import json

    user = request.user

    # -----------------------------
    # ورودی‌ها
    # -----------------------------
    selected_unit_id = request.GET.get("unit_id")
    selected_employee_id = request.GET.get("employee_id")
    year = _int_safe(request.GET.get("year"), None)
    months = _int_safe(request.GET.get("months"), None)  # 3 / 6 / 9 / 12 یا None

    # -----------------------------
    # تعیین واحدها و پرسنل مجاز
    # -----------------------------
    from core.constants import Settings

    units = []
    employees = []

    user = request.user
    ep = getattr(user, "employee_profile", None)

    selected_unit_id = request.GET.get("unit_id")

    if ep:
        # =========================
        # مدیر کارخانه
        # =========================
        if is_factory_manager(user):
            # همه واحدهای سازمان خودش
            units = Unit.objects.filter(
                organization=ep.organization
            ).order_by("name")

            # بعد از انتخاب واحد → پرسنل همان واحد
            if selected_unit_id:
                employees = EmployeeProfile.objects.filter(
                    organization=ep.organization,
                    unit_id=selected_unit_id
                ).order_by("user__last_name", "user__first_name")

        # =========================
        # سایر مدیران (مدیر واحد و …)
        # =========================
        else:
            if ep.unit:
                employees = EmployeeProfile.objects.filter(
                    organization=ep.organization,
                    unit=ep.unit
                ).order_by("user__last_name", "user__first_name")

    # -----------------------------
    # queryset پایه
    # -----------------------------
    qs_base = Evaluation.objects.select_related("template").filter(
        is_archived=False
    )

    # محدودسازی به پرسنل مجاز
    if employees:
        qs_base = qs_base.filter(
            employee_id__in=employees.values_list("personnel_code", flat=True)
        )

    # گزارش فردی
    if selected_employee_id:
        qs_base = qs_base.filter(employee_id=selected_employee_id)

    # -----------------------------
    # سال‌های موجود
    # -----------------------------
    years = list(
        qs_base.values_list("period_start__year", flat=True)
        .distinct()
        .order_by("-period_start__year")
    )
    default_year = years[0] if years else date.today().year
    year = year or default_year

    # -----------------------------
    # فیلتر سال / بازه
    # -----------------------------
    if months in (3, 6, 9, 12):
        qs_temp = qs_base.annotate(
            months_diff=ExpressionWrapper(
                F("period_end") - F("period_start"),
                output_field=fields.DurationField()
            )
        ).filter(period_start__year=year)

        filtered_ids = [
            ev.id for ev in qs_temp
            if ev.months_label() == months
        ]

        qs = qs_base.filter(id__in=filtered_ids)

    else:
        qs = qs_base.filter(period_start__year=year)

    # -----------------------------
    # محاسبه درصد
    # -----------------------------
    percent_expr = Case(
        When(max_score__gt=0, then=(F("final_score") * 100.0) / F("max_score")),
        default=None,
        output_field=FloatField(),
    )

    # -----------------------------
    # آمار خلاصه
    # -----------------------------
    stats = {
        "total": qs.count(),
        "draft": qs.filter(status="draft").count(),
        "submitted": qs.filter(status="submitted").count(),
        "approved": qs.filter(status="approved").count(),
        "avg_percent": round(
            qs.aggregate(avg=Avg(percent_expr))["avg"] or 0.0, 1
        ),
    }

    # -----------------------------
    # نمودارها
    # -----------------------------
    status_pie = {
        "draft": stats["draft"],
        "submitted": stats["submitted"],
        "approved": stats["approved"],
    }

    by_form = list(
        qs.values("template__code")
        .annotate(avg_percent=Coalesce(Avg(percent_expr), 0.0))
        .order_by("template__code")
    )

    status_pie_json = mark_safe(json.dumps(status_pie))
    by_form_json = mark_safe(json.dumps(by_form))

    # -----------------------------
    # context
    # -----------------------------
    context = {
        "years": years,
        "year": year,
        "months": months if months in (3, 6, 9, 12) else "",
        "month_choices": [3, 6, 9, 12],

        "units": units,
        "selected_unit_id": selected_unit_id,
        "employees": employees,
        "employee_id": selected_employee_id,

        "stats": stats,
        "by_form": by_form,
        "status_pie": status_pie,
        "by_form_json": by_form_json,
        "status_pie_json": status_pie_json,
        "avg_percent": stats["avg_percent"],
    }

    return render(request, "manager/reports/dashboard_reports.html", context)

@login_required
def print_dashboard_view(request):
    """چاپ گزارش مدیر (HTML قابل پرینت)"""
    from .reports import reports_dashboard_view  # استفاده از منطق اصلی گزارش

    # فراخوانی ویوی اصلی برای گرفتن context
    response = reports_dashboard_view(request)

    # اگر ویو اصلی یک HttpResponseTemplate بود، context را از آن بگیر
    if hasattr(response, "context_data"):
        context = response.context_data
    elif isinstance(response, dict):
        context = response
    else:
        context = {}

    # افزودن داده‌های اضافی
    context["year"] = request.GET.get("year")
    context["months"] = request.GET.get("months")

    return render(request, "manager/reports/print_dashboard.html", context)

@login_required
def print_evaluation_view(request, eval_id):
    """
    چاپ فرم ارزیابی:
    - ارزیاب خودش یا فرم‌های تأیید نهایی
    - سوپریوزر همه چیز
    """

    # --- دسترسی ---
    base_qs = Evaluation.objects.select_related("template")

    if not request.user.is_superuser:
        base_qs = base_qs.filter(
            Q(evaluator=request.user) |
            Q(status=Evaluation.Status.FINAL_APPROVED)
        )

    ev = get_object_or_404(base_qs, id=eval_id)

    # --------------------------------------------------
    # approvals (HYBRID – مطابق معماری واقعی سیستم)
    # --------------------------------------------------

    role_order = ["UNIT_MANAGER", "HR", "FACTORY_MANAGER"]

    role_labels = {
        "UNIT_MANAGER": "مدیر واحد",
        "HR": "منابع انسانی",
        "FACTORY_MANAGER": "مدیر کارخانه",
    }

    SIG_ROLE_MAP = {
        "HR": ["hr"],
        "FACTORY_MANAGER": ["factory_manager"],
    }

    sigs = list(ev.signatures.all().order_by("-signed_at"))

    def find_sig_for(role_key):
        wanted = set(SIG_ROLE_MAP.get(role_key, []))
        for s in sigs:
            if getattr(s, "role", None) in wanted:
                return s
        return None

    def get_signer_name(sig):
        user = (
            getattr(sig, "signed_by", None)
            or getattr(sig, "user", None)
            or getattr(sig, "actor", None)
        )
        if not user:
            return None
        return user.get_full_name() or user.username or str(user)

    approvals = []

    for role_key in role_order:

        # -------- UNIT MANAGER --------
        if role_key == "UNIT_MANAGER":
            is_approved = ev.status in [
                Evaluation.Status.HR_REVIEW,
                Evaluation.Status.FACTORY_REVIEW,
                Evaluation.Status.FINAL_APPROVED,
            ]

            signed_at = (
                    ev.evaluated_at
                    or ev.submitted_at
                    or ev.updated_at
            )

            approvals.append({
                "role": role_labels[role_key],
                "is_approved": is_approved,
                "signed_at": signed_at if is_approved else None,
                "signed_by": ev.manager_name,  #  اسم واقعی مدیر واحد
            })
            continue

        # -------- HR / FACTORY MANAGER --------
        sig = find_sig_for(role_key)

        approvals.append({
            "role": role_labels[role_key],
            "is_approved": bool(sig),
            "signed_at": sig.signed_at if sig else None,
            #  چون اسم فرد نداریم، اسم نقش رو نشون می‌دیم
            "signed_by": (f"{sig.signed_by_name} "
                          if sig and sig.signed_by_name else role_labels[role_key]),
        })

    # --------------------------------------------------
    # سایر داده‌های فرم
    # --------------------------------------------------

    emp_profile = (
        EmployeeProfile.objects
        .filter(personnel_code=ev.employee_id)
        .select_related("unit")
        .first()
    )
    employee_unit = emp_profile.unit.unit_code if emp_profile else ""

    items = list(
        ev.items
        .select_related("criterion", "selected_option")
        .values(
            "criterion_order",
            "criterion_title",
            "selected_value",
            "earned_points",
            "selected_option__label",
        )
    )

    percent = None
    if ev.final_score and ev.max_score:
        try:
            percent = round(
                float(ev.final_score) / float(ev.max_score) * 100, 2
            )
        except ZeroDivisionError:
            percent = None

    context = {
        "ev": ev,
        "items": items,
        "percent": percent,
        "employee_name": ev.employee_name,
        "employee_id": ev.employee_id,
        "employee_unit": employee_unit,
        "manager_unit": ev.unit_code,
        "manager_name": ev.manager_name,
        "title": f"فرم ارزیابی عملکرد {ev.employee_name}",
        "year": ev.period_start.year if ev.period_start else "",
        "period": ev.period_label,
        "approvals": approvals,
    }

    return render(
        request,
        "manager/reports/print_evaluation.html",
        context
    )

@login_required
def summary_report_view(request):
    user = request.user
    manager_profile = getattr(user, "employee_profile", None)

    if not manager_profile:
        return HttpResponse("پروفایل پیدا نشد!", status=403)

    # ---- تشخیص نوع مدیر ----
    is_factory_manager = (
        manager_profile.job_role
        and manager_profile.job_role.code == Settings.ROLE_FACTORY_MANAGER
    )

    # ---- تعیین واحدها ----
    from core.models import Unit

    if is_factory_manager:
        # مدیر کارخانه → همه واحدهای سازمان خودش
        units_qs = Unit.objects.filter(organization=manager_profile.organization)
    else:
        # مدیر واحد → فقط واحد خودش
        units_qs = Unit.objects.filter(id=manager_profile.unit_id)

    # کد واحدهای تحت مدیریت
    unit_codes = list(units_qs.values_list("unit_code", flat=True))

    # ---- گرفتن ارزیابی‌ها ----
    qs = Evaluation.objects.filter(unit_code__in=unit_codes)

    # ---- سال‌ها ----
    years = list(
        qs.values_list("period_start__year", flat=True)
          .distinct()
          .order_by("-period_start__year")
    )

    # ---- فرم‌ها ----
    form_choices = list(
        FormTemplate.objects.values_list("code", flat=True).order_by("code")
    )

    # ---- فیلترهای GET ----
    selected_year = request.GET.get("year")
    selected_form = request.GET.get("form_code")

    if selected_year:
        qs = qs.filter(period_start__year=selected_year)

    if selected_form:
        qs = qs.filter(template__code=selected_form)

    # ---- محاسبه درصد ----
    from django.db.models import Avg, F, FloatField, Case, When

    percent_expr = Case(
        When(max_score__gt=0, then=(F("final_score") * 100.0) / F("max_score")),
        default=None,
        output_field=FloatField()
    )

    stats = {
        "total": qs.count(),
        "submitted": qs.filter(status="submitted").count(),
        "approved": qs.filter(status="approved").count(),
        "avg_percent": round(qs.aggregate(avg=Avg(percent_expr))["avg"] or 0, 1),
    }

    # ---- نمودارها ----
    status_pie = {
        "draft": qs.filter(status="draft").count(),
        "submitted": qs.filter(status="submitted").count(),
        "approved": qs.filter(status="approved").count(),
    }

    by_form = list(
        qs.values("template__code")
          .annotate(avg_percent=Avg(percent_expr))
          .order_by("template__code")
    )

    import json
    from django.utils.safestring import mark_safe

    status_pie_json = mark_safe(json.dumps(status_pie))
    by_form_json = mark_safe(json.dumps(by_form))

    # ---- خلاصه واحدها ----
    unit_summary = []

    for u in units_qs:
        u_qs = qs.filter(unit_code=u.unit_code)

        total = u_qs.count()
        submitted = u_qs.filter(status="submitted").count()
        approved = u_qs.filter(status="approved").count()

        avg_percent = (
            round(u_qs.aggregate(avg=Avg(percent_expr))["avg"] or 0, 1)
            if total > 0 else 0
        )

        unit_summary.append({
            "name": u.name,
            "code": u.unit_code,
            "total": total,
            "submitted": submitted,
            "approved": approved,
            "avg_percent": avg_percent,
        })

    # ---- ارسال به template ----
    context = {
        "unit_summary": unit_summary,
        "status_pie_json": status_pie_json,
        "by_form_json": by_form_json,
        "by_form": by_form,
        "years": years,
        "form_choices": form_choices,
        "selected_year": selected_year,
        "selected_form": selected_form,
        "stats": stats,
    }

    return render(request, "manager/reports/summary_report.html", context)










