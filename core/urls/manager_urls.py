# core/urls/manager_urls.py
from django.urls import path
from django.views.generic import RedirectView
from core.views.manager.evaluations import (
    dashboard_view, evaluation_list_view, edit_evaluation_view,
    start_evaluation_view, evaluation_save_progress,
    ajax_managers_for_unit, ajax_teams_for_manager,
    bulk_archive_drafts_view, bulk_delete_drafts_view,
    archive_evaluation_view, eval_approve,
)
from core.views.manager.workflow import eval_factory_approve
from core.views.manager import  workflow
from core.views.manager.reports import reports_dashboard_view, print_dashboard_view, print_evaluation_view
from core.views.manager.evaluation_lists import (ArchivedListView,)
from core.views.manager.reports import summary_report_view
from core.views.manager.evaluation_lists import (
    DraftListView,
    SubmittedListView,
    ApprovedListView,
    HRReviewListView,
    ManagerReviewListView,
    FactoryReviewListView,
)
from core.views.manager.approval_actions import (
    approve_evaluation,
    return_evaluation,
)


urlpatterns = [
    path("", RedirectView.as_view(pattern_name="eval_dashboard", permanent=False), name="home"),
    path("eval/dashboard/", dashboard_view, name="eval_dashboard"),
    path("eval/list/<str:status>/", evaluation_list_view, name="eval_list"),
    path("eval/<int:pk>/edit/", edit_evaluation_view, name="eval_edit"),
    path("eval/start/", start_evaluation_view, name="eval_create"),
    path("eval/<int:pk>/save-progress/", evaluation_save_progress, name="eval_save_progress"),

    # Ajax
    path("ajax/units/<str:unit_key>/managers/", ajax_managers_for_unit, name="ajax_managers_for_unit"),
    path("ajax/managers/<int:ep_id>/teams/", ajax_teams_for_manager, name="ajax_teams_for_manager"),

    path("eval/bulk-archive/", bulk_archive_drafts_view, name="eval_bulk_archive"),
    path("eval/bulk-delete/", bulk_delete_drafts_view, name="eval_bulk_delete"),
    path("eval/<int:pk>/archive/", archive_evaluation_view, name="eval_archive"),
    path("eval/<int:pk>/approve/", eval_approve, name="eval_approve"),
    path("eval/reports/", reports_dashboard_view, name="eval_reports"),
    path("eval/reports/print/", print_dashboard_view, name="eval_reports_print"),
    path("eval/reports/print-evaluation/<int:eval_id>/", print_evaluation_view, name="eval_print_evaluation"),

    # لیست پیش‌نویس‌ها
    path("evaluations/drafts/", DraftListView.as_view(), name="manager_evaluations_drafts",),
    # لیست ثبت‌شده‌ها (Submitted)
    path("evaluations/submitted/", SubmittedListView.as_view(),name="manager_evaluations_submitted",),
    # لیست تاییدشده‌ها (Approved)
    path("evaluations/approved/", ApprovedListView.as_view(), name="manager_evaluations_approved",),
    # لیست آرشیوشده‌ها (Archived)
    path("evaluations/archived/", ArchivedListView.as_view(), name="manager_evaluations_archived",),

    path("reports/summary/", summary_report_view, name="manager_summary_report"),
    path("evaluations/draft/", DraftListView.as_view(), name="draft_list"),
    path("evaluations/submitted/", SubmittedListView.as_view(), name="submitted_list"),
    path("evaluations/approved/", ApprovedListView.as_view(), name="approved_list"),

    # مراحل جدید گردش کار
    path("workflow/", workflow.workflow_view, name="workflow"),
    path("evaluations/hr-review/", HRReviewListView.as_view(), name="hr_review_list"),
    path("evaluations/manager-review/", ManagerReviewListView.as_view(), name="manager_review_list"),
    path("evaluations/factory-review/", FactoryReviewListView.as_view(), name="factory_review_list"),

   path("eval/<int:pk>/approve/", approve_evaluation, name="eval_approve"),
   path("eval/<int:pk>/return/", return_evaluation, name="eval_return"),
path(
    "workflow/<int:pk>/factory-approve/",
    eval_factory_approve,
    name="eval_factory_approve",
),

]
