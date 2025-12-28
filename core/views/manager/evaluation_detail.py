#core/views/manager/evaluation_detail.py
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from core.models import Evaluation
from core.approval.workflow_engine import WorkflowEngine

@login_required
def evaluation_detail(request, pk):
    ev = get_object_or_404(Evaluation, pk=pk)
    # فقط مدیر ارزیاب در حالت draft می‌تواند ویرایش کند
    can_edit = (
            ev.status == Evaluation.Status.DRAFT
            and ev.evaluator_id == request.user.id
    )
    engine = WorkflowEngine(ev)

    context = {
        "evaluation": ev,
        "ev": ev,
        "can_edit": can_edit,
        "read_only": not can_edit,
        "can_approve": engine.can_approve(request.user),
    }

    return render(request, "manager/evaluations/detail.html", context)
