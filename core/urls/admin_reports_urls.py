# core/urls/admin_reports_urls.py
from django.urls import path
from django.contrib.admin.views.decorators import staff_member_required
from django.views.generic import TemplateView
from core.views.admin import reports_api

app_name = "reports"

urlpatterns = [
    # 📄 صفحه اصلی گزارش‌ها (قالب evaluation_report.html)
    path("evaluation-report/", staff_member_required(TemplateView.as_view(template_name="admin/reports/evaluation_report.html")), name="evaluation_report"),
    path("get_managers/", staff_member_required(reports_api.get_managers_api), name="get_managers"),
    path("get_jobroles/", staff_member_required(reports_api.get_jobroles_api), name="get_jobroles"),
    path("get_units_by_org/", staff_member_required(reports_api.get_units_by_org), name="get_units_by_org"),

    # 🔹 APIها
    path("employees/", staff_member_required(reports_api.employees_api), name="employees_api"),
    path("data/", staff_member_required(reports_api.data_api), name="data_api"),

    # 🖨 مسیرهای چاپ و PDF
    #path("print-form/", staff_member_required(reports.print_form_view), name="print_form_view"),
    #path("print-form-pdf/", staff_member_required(reports.print_form_pdf), name="print_form_pdf"),
]
