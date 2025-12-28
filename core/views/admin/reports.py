# core/views/admin/reports.py
from django.contrib import admin
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import path
from django.views.decorators.http import require_GET
from core.models import Unit, EmployeeProfile, Evaluation, Organization
import csv
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
# ---------- برای ویوهای جدید چاپ و PDF ----------
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.http import HttpResponse
from io import BytesIO
from core.mixins.organization_scope import scope_queryset
from django.utils.decorators import method_decorator

class EvaluationReportAdmin(admin.ModelAdmin):
    """
    صفحه گزارش در ادمین + ۲ API:
      - /employees/ : لیست پرسنل یک واحد
      - /data/: داده نمودار (فردی/تجمیعی)
    """
    change_list_template = "admin/reports/evaluation_report.html"

    # فقط دیدن
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("employees/", self.admin_site.admin_view(self.employees_api), name="reports_employees_api"),
            path("data/", self.admin_site.admin_view(self.data_api), name="reports_data_api"),
            path("export/csv/", self.admin_site.admin_view(self.export_csv), name="reports_export_csv"),
            path("export/pdf/", self.admin_site.admin_view(self.export_pdf), name="reports_export_pdf"),
            path("load-units/", self.admin_site.admin_view(self.load_units_api), name="reports_load_units"),
            path("print-form/", self.admin_site.admin_view(self.print_form_view), name="reports_print_form"),
        ]
        return custom + urls

    # -----------------------------
    # 📁 خروجی CSV و PDF
    # -----------------------------

    @method_decorator(require_GET)
    def export_csv(self, request):

        mode = request.GET.get("mode", "unit")
        unit_id = request.GET.get("unit_id")
        if not unit_id:
            return HttpResponse("unit_id required", status=400)

        unit = Unit.objects.filter(id=unit_id).first()
        if not unit:
            return HttpResponse("unit not found", status=404)

        # فیلتر زمانی
        year = request.GET.get("year")
        period = int(request.GET.get("period", 12))  # ماه
        date_filter = {}
        if year:
            from datetime import date, timedelta
            start_year = date(int(year), 1, 1)
            end_year = date(int(year) + 1, 1, 1)
            date_filter["period_start__gte"] = start_year
            date_filter["period_start__lt"] = end_year

        # برای بازه‌ی ماه‌ها، فقط آخر N ماه آخر داده‌ها را نگه می‌داریم
        if period and period < 12:
            from datetime import date, timedelta
            today = date.today()
            cutoff = today - timedelta(days=30 * period)
            date_filter["period_start__gte"] = cutoff

        # اگر حالت فردی است، فیلترش می‌کنیم
        employee_filter = {}
        if mode == "individual":
            emp_id = request.GET.get("employee_id")
            if not emp_id:
                return HttpResponse("employee_id required", status=400)
            ep = EmployeeProfile.objects.select_related("user").filter(id=emp_id).first()
            if not ep:
                return HttpResponse("employee not found", status=404)
            candidate_ids = []
            if ep.personnel_code: candidate_ids.append(ep.personnel_code.strip())
            if ep.user_id: candidate_ids.append(str(ep.user_id))
            employee_filter["employee_id__in"] = candidate_ids

        qs = (Evaluation.objects
              .filter(unit_code=(unit.unit_code or "").strip(), **employee_filter)
              .order_by("employee_id", "period_start"))
        qs = scope_queryset(qs, user=request.user)

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        filename = f"evaluation_report_{mode}_{unit.unit_code or 'unit'}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(["Employee Code", "Username", "Status", "Final Score", "Max Score", "Percent", "Period Start"])

        # برای نام لاتین از username و کد استفاده می‌کنیم (نه نام فارسی)
        for ev in qs:
            # سعی می‌کنیم username را از پروفایل پیدا کنیم (اختیاری، امن)
            username = ""
            ep = EmployeeProfile.objects.select_related("user").filter(personnel_code=ev.employee_id).first()
            if not ep and (ev.employee_id or "").isdigit():
                ep = EmployeeProfile.objects.select_related("user").filter(user_id=int(ev.employee_id)).first()
            if ep and ep.user:
                username = ep.user.username

            percent = ""
            if ev.final_score and ev.max_score:
                try:
                    percent = round(float(ev.final_score) / float(ev.max_score) * 100.0, 2)
                except Exception:
                    percent = ""
            writer.writerow([
                ev.employee_id or "",  # لاتین
                username,  # لاتین
                ev.status or "",
                ev.final_score or "",
                ev.max_score or "",
                percent,
                ev.period_start or "",
            ])

        return response

    @method_decorator(require_GET)
    def export_pdf(self, request):

        mode = request.GET.get("mode", "unit")
        unit_id = request.GET.get("unit_id")
        if not unit_id:
            return HttpResponse("unit_id required", status=400)

        unit = Unit.objects.filter(id=unit_id).first()
        if not unit:
            return HttpResponse("unit not found", status=404)

        # فیلتر حالت فردی (مثل CSV)
        employee_filter = {}
        title_suffix = f"Unit {unit.unit_code or '—'}"
        if mode == "individual":
            emp_id = request.GET.get("employee_id")
            if not emp_id:
                return HttpResponse("employee_id required", status=400)
            ep = EmployeeProfile.objects.select_related("user").filter(id=emp_id).first()
            if not ep:
                return HttpResponse("employee not found", status=404)
            candidate_ids = []
            if ep.personnel_code: candidate_ids.append(ep.personnel_code.strip())
            if ep.user_id: candidate_ids.append(str(ep.user_id))
            employee_filter["employee_id__in"] = candidate_ids
            title_suffix += f" – Employee {ep.user.username if ep and ep.user else (ep.personnel_code or '')}"

        qs = (Evaluation.objects
              .filter(unit_code=(unit.unit_code or "").strip(), **employee_filter)
              .order_by("employee_id", "period_start"))
        qs = scope_queryset(qs, user=request.user)

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
        styles = getSampleStyleSheet()
        story = []

        # عنوان انگلیسی (تماماً لاتین)
        story.append(Paragraph("<b>Performance Evaluation Report</b>", styles["Title"]))
        story.append(Paragraph(title_suffix, styles["Heading3"]))
        story.append(Spacer(1, 10))

        data = [["Employee Code", "Username", "Status", "Final Score", "Max Score", "Percent", "Period Start"]]

        for ev in qs:
            username = ""
            ep = EmployeeProfile.objects.select_related("user").filter(personnel_code=ev.employee_id).first()
            if not ep and (ev.employee_id or "").isdigit():
                ep = EmployeeProfile.objects.select_related("user").filter(user_id=int(ev.employee_id)).first()
            if ep and ep.user:
                username = ep.user.username

            percent = ""
            if ev.final_score and ev.max_score:
                try:
                    percent = f"{round(float(ev.final_score) / float(ev.max_score) * 100.0, 2)}%"
                except Exception:
                    percent = ""

            data.append([
                ev.employee_id or "",
                username,
                ev.status or "",
                ev.final_score or "-",
                ev.max_score or "-",
                percent,
                str(ev.period_start or ""),
            ])

        table = Table(data, repeatRows=1, hAlign="LEFT", colWidths=[80, 80, 60, 70, 70, 60, 80])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 1), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ]))

        story.append(table)
        doc.build(story)

        buffer.seek(0)
        response = HttpResponse(buffer, content_type="application/pdf")
        filename = f"evaluation_report_{mode}_{unit.unit_code or 'unit'}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def changelist_view(self, request, extra_context=None):
        """
        اگر؟format=units بیاد: لیست واحدها را JSON بده؛
        در غیر این صورت، صفحه استاندارد change_list را رندر کن تا context کامل (cl/opts/...) داشته باشیم.
        """
        extra_context = extra_context or {}
        extra_context["organizations"] = Organization.objects.all().order_by("name")

        if request.GET.get("format") == "units":
            units = scope_queryset(Unit.objects.order_by("name"), user=request.user) \
                .values("id", "name", "unit_code")
            return JsonResponse({"units": list(units)})
        return super().changelist_view(request, extra_context=extra_context)

    @method_decorator(require_GET)
    def employees_api(self, request):
        unit_id = request.GET.get("unit_id")
        if not unit_id:
            return HttpResponseBadRequest("unit_id is required")

        qs = (EmployeeProfile.objects
              .select_related("user", "unit")
              .filter(unit_id=unit_id)
              .order_by("user__last_name", "user__first_name"))
        qs = scope_queryset(qs, user=request.user)

        data = [{
            "id": ep.id,
            "text": f"{ep.full_name} — {(ep.title or '').strip()}".strip(" —"),
            # در صورت نیاز این‌ها را هم برگردان (اینجا لازم نداریم)
            # "personnel_code": ep.personnel_code,
            # "user_id": ep.user_id,
        } for ep in qs]

        return JsonResponse({"results": data})

    @method_decorator(require_GET)
    def data_api(self, request):
        """
        نسخه بهینه‌شده — بدون حلقه for
        فیلترها: واحد، سال، بازه، نوع فرم (۳،۶،۹،۱۲)، و حالت فردی/تجمیعی
        خروجی: نمودار خطی، دایره‌ای، خلاصه
        """
        from datetime import date, datetime
        from django.db.models import (
            Avg, Count, F, FloatField, Value, Case, When, ExpressionWrapper, IntegerField
        )
        from django.db.models.functions import ExtractYear, ExtractMonth
        from dateutil.relativedelta import relativedelta

        try:
            mode = request.GET.get("mode", "individual")
            unit_id = request.GET.get("unit_id")
            if not unit_id:
                return JsonResponse({"error": "unit_id is required"}, status=400)

            unit = Unit.objects.filter(id=unit_id).only("id", "name", "unit_code").first()
            if not unit:
                return JsonResponse({"error": "unit not found"}, status=404)
            unit_code = (unit.unit_code or "").strip()

            # ---------- فیلترهای ورودی ----------
            year_param = request.GET.get("year")
            period_param = request.GET.get("period")  # 3 / 6 / 9 / 12
            from_date = request.GET.get("from_date")
            to_date = request.GET.get("to_date")

            # پایهٔ فیلترها
            base_filters = {"unit_code": unit_code}

            # سال
            if year_param:
                y = int(year_param)
                start = date(y, 1, 1)
                end = date(y + 1, 1, 1)
                base_filters["period_start__gte"] = start
                base_filters["period_start__lt"] = end

            # بازه تاریخ دستی
            if from_date and to_date:
                f_date = datetime.fromisoformat(from_date).date()
                t_date = datetime.fromisoformat(to_date).date()
                base_filters["period_start__range"] = (f_date, t_date)

            # فیلتر اختلاف ماه بین start و end (بدون حلقه)
            qs_eval = Evaluation.objects.annotate(
                diff_months=ExpressionWrapper(
                    (ExtractYear(F("period_end")) - ExtractYear(F("period_start"))) * 12 +
                    (ExtractMonth(F("period_end")) - ExtractMonth(F("period_start"))),
                    output_field=IntegerField()
                )
            ).filter(**base_filters)
            qs_eval = scope_queryset(qs_eval, user=request.user)

            if period_param and period_param.isdigit():
                qs_eval = qs_eval.filter(diff_months=int(period_param))

            # فیلتر فقط فرم‌های دارای امتیاز
            eval_filters = {**base_filters, "status": Evaluation.Status.APPROVED}
            pie_filters = {**base_filters}

            # درصد امن
            avg_percent_expr = ExpressionWrapper(
                100.0 * F("final_score") / F("max_score"),
                output_field=FloatField()
            )
            safe_percent_expr = Case(
                When(final_score__isnull=False, max_score__isnull=False, then=avg_percent_expr),
                default=Value(None), output_field=FloatField()
            )

            # ---------- حالت فردی ----------
            if mode == "individual":
                employee_id = request.GET.get("employee_id")
                if not employee_id:
                    return JsonResponse({"error": "employee_id is required"}, status=400)

                ep = EmployeeProfile.objects.select_related("user").filter(id=employee_id).first()
                if not ep:
                    return JsonResponse({"error": "employee not found"}, status=404)

                candidate_ids = []
                if ep.personnel_code:
                    candidate_ids.append(ep.personnel_code.strip())
                if ep.user_id:
                    candidate_ids.append(str(ep.user_id))
                if not candidate_ids:
                    return JsonResponse({
                        "chart": {"title": f"No data for {ep.full_name}", "labels": [], "datasets": []},
                        "summary": {"unit": unit.name, "employee": ep.full_name, "count": 0, "avg": 0.0},
                    })

                qs_eval = qs_eval.filter(employee_id__in=candidate_ids)

                evals = (qs_eval.filter(status=Evaluation.Status.APPROVED)
                         .exclude(final_score__isnull=True, max_score__isnull=True)
                         .order_by("period_start")
                         .values("period_start")
                         .annotate(avg_pct=Avg(safe_percent_expr), cnt=Count("id")))

                labels = [e["period_start"].isoformat() if e["period_start"] else "—" for e in evals]
                series = [float(e["avg_pct"] or 0.0) for e in evals]

                summary = (qs_eval.filter(status=Evaluation.Status.APPROVED)
                           .exclude(final_score__isnull=True, max_score__isnull=True)
                           .aggregate(avg=Avg(avg_percent_expr), count=Count("id")))

                # Pie Chart وضعیت‌ها
                status_map = {
                    "draft": "پیش‌نویس", "submitted": "ارسال‌شده",
                    "approved": "تأییدشده", "archived": "آرشیوشده", "expired": "منقضی‌شده"
                }
                status_counts = (qs_eval.values("status")
                                 .annotate(cnt=Count("id"))
                                 .order_by("status"))
                pie_labels = [status_map.get(s["status"], s["status"]) for s in status_counts]
                pie_data = [s["cnt"] for s in status_counts] or [1]
                if not status_counts:
                    pie_labels = ["بدون داده"]

                return JsonResponse({
                    "chart": {
                        "title": f"میانگین امتیاز (%) – {ep.full_name}",
                        "labels": labels,
                        "datasets": [{"label": "میانگین درصد", "data": series}],
                    },
                    "summary": {
                        "unit": unit.name,
                        "employee": ep.full_name,
                        "count": int(summary.get("count") or 0),
                        "avg": float(summary.get("avg") or 0.0),
                    },
                    "pie": {
                        "title": "توزیع وضعیت فرم‌ها",
                        "labels": pie_labels,
                        "data": pie_data,
                    },
                })

            # ---------- حالت تجمیعی (واحد) ----------
            evals = (qs_eval.filter(status=Evaluation.Status.APPROVED)
                     .exclude(final_score__isnull=True, max_score__isnull=True)
                     .order_by("period_start")
                     .values("period_start")
                     .annotate(avg_pct=Avg(safe_percent_expr), cnt=Count("id")))

            labels = [e["period_start"].isoformat() if e["period_start"] else "—" for e in evals]
            series = [float(e["avg_pct"] or 0.0) for e in evals]

            summary = (qs_eval.filter(status=Evaluation.Status.APPROVED)
                       .exclude(final_score__isnull=True, max_score__isnull=True)
                       .aggregate(avg=Avg(avg_percent_expr), count=Count("id")))

            status_map = {
                "draft": "پیش‌نویس", "submitted": "ارسال‌شده",
                "approved": "تأییدشده", "archived": "آرشیوشده", "expired": "منقضی‌شده"
            }
            status_counts = (qs_eval.values("status")
                             .annotate(cnt=Count("id"))
                             .order_by("status"))
            pie_labels = [status_map.get(s["status"], s["status"]) for s in status_counts]
            pie_data = [s["cnt"] for s in status_counts] or [1]
            if not status_counts:
                pie_labels = ["بدون داده"]

            return JsonResponse({
                "chart": {
                    "title": f"میانگین امتیاز (%) – واحد {unit.name}",
                    "labels": labels,
                    "datasets": [{"label": "میانگین درصد", "data": series}],
                },
                "summary": {
                    "unit": unit.name,
                    "employee": None,
                    "count": int(summary.get("count") or 0),
                    "avg": float(summary.get("avg") or 0.0),
                },
                "pie": {
                    "title": "توزیع وضعیت فرم‌ها",
                    "labels": pie_labels,
                    "data": pie_data,
                },
            })

        except Exception as e:
            import traceback
            return JsonResponse({
                "error": str(e),
                "trace": traceback.format_exc().splitlines()[-6:]
            }, status=500)

    @method_decorator(require_GET)
    def load_units_api(self, request):
        org_id = request.GET.get("org_id")
        if not org_id:
            return JsonResponse({"units": []})

        units = Unit.objects.filter(organization_id=org_id).order_by("name")
        data = [{"id": u.id, "name": u.name} for u in units]

        return JsonResponse({"units": data})

    # ---------- چاپ فرم ارزیابی ----------

    @method_decorator(staff_member_required)
    def print_form_view(self, request, *args, **kwargs):
        """خروجی HTML قابل پرینت برای فرم ارزیابی در ادمین"""
        employee_id = request.GET.get("employee_id")
        unit_id = request.GET.get("unit_id")
        year = request.GET.get("year")
        period = request.GET.get("period")

        if not employee_id:
            return HttpResponse("پارامتر کارمند الزامی است", status=400)

        emp = EmployeeProfile.objects.select_related("user", "unit").filter(id=employee_id).first()
        if not emp:
            return HttpResponse("کارمند یافت نشد", status=404)

        # واکشی فرم تأییدشده
        filters = {"status": Evaluation.Status.APPROVED, "employee_id": emp.personnel_code}
        if year:
            filters["period_start__year"] = int(year)

        evals = Evaluation.objects.filter(**filters).order_by("-period_start")
        evals = scope_queryset(evals, user=request.user)

        if period and period.isdigit():
            from django.db.models import F, IntegerField, ExpressionWrapper
            from django.db.models.functions import ExtractYear, ExtractMonth

            diff_expr = ExpressionWrapper(
                (ExtractYear(F("period_end")) - ExtractYear(F("period_start"))) * 12
                + (ExtractMonth(F("period_end")) - ExtractMonth(F("period_start"))),
                output_field=IntegerField(),
            )
            evals = evals.annotate(month_diff=diff_expr).filter(month_diff=int(period))

        ev = evals.first()
        if not ev:
            return HttpResponse("هیچ ارزیابی یافت نشد", status=404)

        # ✅ آیتم‌های فرم از snapshot داخلی مدل
        items = list(
            ev.items.select_related("criterion", "selected_option").values(
                "criterion_order",
                "criterion_title",
                "selected_value",
                "earned_points",
                "selected_option",
                "selected_option__label",
            )
        )

        context = {
            "title": "فرم ارزیابی عملکرد پرسنل",
            "employee": emp,
            "unit_code": ev.unit_code or (emp.unit.unit_code if emp.unit else "-"),
            "manager_name": ev.manager_name or "—",
            "year": year or (ev.period_start.year if ev.period_start else ""),
            "period": ev.period_label if hasattr(ev, "period_label") else "",
            "items": items,
            "total_score": ev.final_score or 0,
            "max_score": ev.max_score or 0,
            "total_percent": (
                round(100 * float(ev.final_score) / float(ev.max_score), 2)
                if ev.final_score and ev.max_score
                else None
            ),
        }

        return render(request, "admin/reports/print_form.html", context)

    # ---------- خروجی PDF فرم ----------
    @staff_member_required
    def print_form_pdf(request):
        """دانلود PDF فرم"""
        from django.template.loader import get_template
        from io import BytesIO
        from xhtml2pdf import pisa
        employee_id = request.GET.get("employee_id")
        unit_id = request.GET.get("unit_id")

        if not employee_id or not unit_id:
            return HttpResponse("پارامترها ناقص است", status=400)

        emp = EmployeeProfile.objects.select_related("user").filter(id=employee_id).first()
        unit = Unit.objects.filter(id=unit_id).first()
        year = request.GET.get("year")
        period = request.GET.get("period")

        # فیلتر پایه
        filters = {
            "employee_id": emp.personnel_code,
            "status": Evaluation.Status.APPROVED,
        }

        # فیلتر سال
        if year:
            from datetime import date
            start = date(int(year), 1, 1)
            end = date(int(year) + 1, 1, 1)
            filters["period_start__gte"] = start
            filters["period_start__lt"] = end

        # فیلتر دوره (3،6،9،12)
        if period and period.isdigit():
            from django.db.models import F, IntegerField, ExpressionWrapper
            from django.db.models.functions import ExtractYear, ExtractMonth

            diff_expr = ExpressionWrapper(
                (ExtractYear(F("period_end")) - ExtractYear(F("period_start"))) * 12 +
                (ExtractMonth(F("period_end")) - ExtractMonth(F("period_start"))),
                output_field=IntegerField()
            )

            evals = (Evaluation.objects.annotate(month_diff=diff_expr)
                     .filter(**filters, month_diff=int(period))
                     .order_by("-period_start"))
            evals = scope_queryset(evals, user=request.user)

        else:
            evals = Evaluation.objects.filter(**filters).order_by("-period_start")

        template = get_template("admin/print_form.html")
        html = template.render({"employee": emp, "unit": unit, "evaluations": evals})
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="evaluation_{emp.personnel_code}.pdf"'
        pisa.CreatePDF(BytesIO(html.encode("utf-8")), dest=response, encoding="utf-8")
        return response

# ---------- مدل مجازی فقط برای گزارش ----------
from core.models import Unit

class EvaluationReport(Unit):
    class Meta:
        proxy = True
        verbose_name = "گزارش ارزیابی"
        verbose_name_plural = "گزارش‌های ارزیابی"

# رجیستر در ادمین
#admin.site.register(EvaluationReport, EvaluationReportAdmin)


