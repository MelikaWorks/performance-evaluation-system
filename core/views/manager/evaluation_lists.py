# core/views/manager/evaluation_lists.py
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from core.models import Evaluation
from core.constants import Settings

@method_decorator(login_required, name="dispatch")
class BaseEvaluationListView(ListView):

    model = Evaluation
    paginate_by = 20
    template_name = "manager/evaluations/evaluation_lists.html"

    list_title = "لیست ارزیابی‌ها"
    status_filter = None

    def base_queryset(self):
        """
        فقط ارزیابی‌های همین مدیر که هنوز آرشیو نشده‌اند
        (برای Draft / Submitted / Approved)
        """
        return Evaluation.objects.filter(
            evaluator=self.request.user,
            is_archived=False,
        )

    def apply_filters(self, qs):
        """فیلترهای جستجو روی queryset"""
        name = self.request.GET.get("q_name")
        personnel = self.request.GET.get("q_personnel")
        year = self.request.GET.get("q_year")
        form_code = self.request.GET.get("q_form")

        if name:
            qs = qs.filter(employee_name__icontains=name)

        if personnel:
            qs = qs.filter(employee_id__icontains=personnel)

        if year:
            qs = qs.filter(period_start__year=year)

        if form_code:
            qs = qs.filter(template__code=form_code)

        return qs

    def dispatch(self, request, *args, **kwargs):
        from core.services.evaluation_access import (
            is_hr,
            is_unit_manager,
            is_factory_manager,
        )
        from django.http import HttpResponseForbidden

        # لیست HR فقط برای HR
        if isinstance(self, HRReviewListView):
            if not is_hr(request.user):
                return HttpResponseForbidden("شما اجازه مشاهده این لیست را ندارید.")

        # لیست مدیر واحد فقط برای مدیر واحد
        if isinstance(self, ManagerReviewListView):
            if not is_unit_manager(request.user):
                return HttpResponseForbidden("شما اجازه مشاهده این لیست را ندارید.")

        # لیست مدیر کارخانه فقط برای مدیر کارخانه
        if isinstance(self, FactoryReviewListView):
            if not is_factory_manager(request.user):
                return HttpResponseForbidden("شما اجازه مشاهده این لیست را ندارید.")

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = self.base_queryset()

        if self.status_filter:
            qs = qs.filter(status=self.status_filter)

        qs = self.apply_filters(qs)
        return qs.order_by("-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = self.list_title
        ctx["querystring"] = "&" + "&".join(
            f"{k}={v}" for k, v in self.request.GET.items() if k != "page"
        )
        return ctx

class DraftListView(BaseEvaluationListView):
    list_title = "لیست پیش‌نویس‌ها (Draft)"
    status_filter = Evaluation.Status.DRAFT

class SubmittedListView(BaseEvaluationListView):
    list_title = "لیست ارسال‌شده‌ها (Submitted)"
    status_filter = Evaluation.Status.SUBMITTED

class ApprovedListView(BaseEvaluationListView):
    list_title = "لیست تأیید نهایی شده‌ها"
    status_filter = Evaluation.Status.FINAL_APPROVED

    def get_queryset(self):
        user = self.request.user
        ep = getattr(user, "employee_profile", None)

        # مدیر کارخانه → همه فرم‌های تأیید نهایی‌شده
        if ep and ep.job_role and ep.job_role.code == Settings.ROLE_FACTORY_MANAGER:
            qs = Evaluation.objects.filter(
                status=Evaluation.Status.FINAL_APPROVED,
                is_archived=False,
            )
            qs = self.apply_filters(qs)
            return qs.order_by("-id")

        # سایر نقش‌ها → فقط فرم‌هایی که خودشان ارزیاب بوده‌اند
        qs = Evaluation.objects.filter(
            evaluator=user,
            status=Evaluation.Status.FINAL_APPROVED,
            is_archived=False,
        )
        qs = self.apply_filters(qs)
        return qs.order_by("-id")


class ArchivedListView(BaseEvaluationListView):
    list_title = "لیست آرشیوشده‌ها (Archived)"

    def get_queryset(self):
        qs = Evaluation.objects.filter(
            evaluator=self.request.user,
            is_archived=True,
        )
        qs = self.apply_filters(qs)
        return qs.order_by("-id")

class HRReviewListView(BaseEvaluationListView):
    list_title = "لیست در انتظار بررسی HR"
    status_filter = Evaluation.Status.HR_REVIEW


class ManagerReviewListView(BaseEvaluationListView):
    list_title = "لیست در انتظار بررسی مدیر واحد"
    status_filter = Evaluation.Status.MANAGER_REVIEW


class FactoryReviewListView(BaseEvaluationListView):
    list_title = "لیست در انتظار بررسی مدیر کارخانه"
    status_filter = Evaluation.Status.FACTORY_REVIEW
