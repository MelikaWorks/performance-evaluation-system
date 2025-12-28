#core/views/manager/approval_actions.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from core.models import Evaluation
from core.approval.workflow_engine import WorkflowEngine

@login_required
@require_POST
def approve_evaluation(request, pk):
    ev = get_object_or_404(Evaluation, pk=pk)
    engine = WorkflowEngine(ev)
    engine.approve(request.user)
    return redirect(request.META.get("HTTP_REFERER", "/"))

@login_required
@require_POST
def return_evaluation(request, pk):
    ev = get_object_or_404(Evaluation, pk=pk)
    engine = WorkflowEngine(ev)
    engine.return_for_edit(request.user)
    return redirect(request.META.get("HTTP_REFERER", "/"))
