#core/views/manager/workflow.py
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from core.models import Evaluation
from core.constants import Settings
from core.approval.workflow_engine import WorkflowEngine
from core.approval.statuses import EvaluationStatus
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.http import HttpResponseForbidden
from django.contrib import messages
from core.models import Unit


@login_required
@require_http_methods(["GET"])
def workflow_view(request):
    ep = getattr(request.user, "employee_profile", None)

    # ------------------ تشخیص نقش‌ها ------------------
    is_factory_manager = (
        ep
        and ep.job_role
        and ep.job_role.code == Settings.ROLE_FACTORY_MANAGER
    )

    is_hr_manager = (
        ep
        and ep.unit
        and ep.job_role
        and ep.unit.unit_code in Settings.HR_UNIT_CODES
        and ep.job_role.code == Settings.ROLE_UNIT_MANAGER
    )
    units_map = {
        u.unit_code: u.name
        for u in Unit.objects.all()
    }

    # ------------------ شمارنده‌ها ------------------
    manager_count = Evaluation.objects.filter(
        status=EvaluationStatus.SUBMITTED
    ).count()

    hr_count = Evaluation.objects.filter(
        status=EvaluationStatus.SUBMITTED
    ).count()

    factory_count = Evaluation.objects.filter(
        status=EvaluationStatus.FACTORY_REVIEW
    ).count()

    final_count = Evaluation.objects.filter(
        status=EvaluationStatus.FINAL_APPROVED
    ).count()

    # ------------------ لیست HR ------------------
    hr_list = []
    if is_hr_manager:
        hr_items = (
            Evaluation.objects
            .filter(status=EvaluationStatus.SUBMITTED)
            .select_related("template", "evaluator", "holding")
            .order_by("-updated_at")
        )

        for ev in hr_items:
            engine = WorkflowEngine(ev)
            ev.unit_name = units_map.get(ev.unit_code, "—")
            hr_list.append({
                "ev": ev,
                "can_approve": engine.can_approve(request.user),
            })

    # ------------------ لیست مدیر کارخانه ------------------
    factory_list = []
    if is_factory_manager:
        factory_items = (
            Evaluation.objects
            .filter(status=EvaluationStatus.FACTORY_REVIEW)
            .select_related("template", "evaluator", "holding")
            .order_by("-updated_at")
        )

        for ev in factory_items:
            engine = WorkflowEngine(ev)
            ev.unit_name = units_map.get(ev.unit_code, "—")  # ← این خط رو اضافه کن
            factory_list.append({
                "ev": ev,
                "can_approve": engine.can_approve(request.user),
            })

    context = {
        "manager_count": manager_count,
        "hr_count": hr_count,
        "factory_count": factory_count,
        "final_count": final_count,
        "hr_list": hr_list,
        "factory_list": factory_list,
    }

    return render(request, "manager/evaluations/workflow.html", context)


@login_required
@require_POST
def eval_factory_approve(request, pk):
    ev = get_object_or_404(Evaluation, pk=pk)
    engine = WorkflowEngine(ev)

    # فقط مدیر کارخانه
    ep = getattr(request.user, "employee_profile", None)
    if not ep or ep.job_role.code != Settings.ROLE_FACTORY_MANAGER:
        return HttpResponseForbidden("اجازه تأیید نهایی ندارید.")

    if not engine.can_user_approve(request.user):
        return HttpResponseForbidden("در این مرحله مجاز نیستید.")

    engine.approve(request.user)
    messages.success(request, "ارزیابی با موفقیت تأیید نهایی شد.")
    return redirect("manager:workflow")

