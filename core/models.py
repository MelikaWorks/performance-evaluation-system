# /models.py
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from .organization_models import (
    Holding,
    DepartmentGroup,
    BaseScopedModel,
)

__all__ = [
    "Holding",
    "DepartmentGroup",
    "BaseScopedModel",
    # + بقیه مدل‌هایی که همین فایل تعریف می‌کنی
]

class Organization(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    city_code = models.CharField(max_length=10, blank=True, null=True)
    is_head = models.BooleanField(default=False)

    holding = models.ForeignKey(
        "Holding",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="organizations"
    )

    class Meta:
        ordering = ["holding__name", "city_code", "name"]
    def __str__(self):
        return self.name

#---------------------------------------
class Unit(models.Model):
    organization = models.ForeignKey(
        "Organization",
    on_delete=models.CASCADE,
    related_name="units"
    )
    name = models.CharField(max_length=255)
    parent_unit = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="sub_units"
    )
    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="managed_units"
    )

    head = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="headed_units"
    )

    unit_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True
    )
    SUPERVISION_POLICIES = (
        ("DEFAULT", "DEFAULT"),
        ("HEADS_ONLY", "HEADS_ONLY"),
        ("EXTERNAL_CHAIN", "EXTERNAL_CHAIN"),
    )
    supervision_policy = models.CharField(
        max_length=32,
        choices=SUPERVISION_POLICIES,
        default="DEFAULT",
    )
    # --- ارتباط با ساختار سازمانی ---
    holding = models.ForeignKey("core.Holding", on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        unique_together = ("organization", "name")

    def __str__(self):
        return self.name

#---------------------------------------
class JobRole(models.Model):
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="job_roles"
    )
    allowed_units = models.ManyToManyField("Unit", related_name="job_roles", blank=True)

    def __str__(self):
        return self.name
#-------------------------------------------
class JobTitle(models.Model):
    name = models.CharField(max_length=255)
    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="job_titles"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("name", "unit")
        ordering = ["unit__unit_code", "name"]

    def __str__(self):
        return f"{self.name} — {self.unit.name}"
#-------------------------------------------
class EmployeeProfile(models.Model):
    def clean(self):
        # هماهنگی کد پرسنلی با یوزرنیم
        if self.user and self.personnel_code and self.user.username != self.personnel_code:
            raise ValidationError('کد پرسنلی باید با نام کاربری (کد پرسنلی کاربر) یکسان باشد.')

    def save(self, *a, **kw):
        # اگر خالی است، از یوزرنیم پر کن (راحت‌ترین سناریو)
        if not self.personnel_code and self.user:
            self.personnel_code = self.user.username
        super().save(*a, **kw)

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="employee_profile"
    )
    organization = models.ForeignKey(
        "Organization", on_delete=models.CASCADE, related_name="employees"
    )
    unit = models.ForeignKey(
        "Unit", on_delete=models.SET_NULL, blank=True, null=True, related_name="employees"
    )
    job_role = models.ForeignKey(
        "JobRole", on_delete=models.SET_NULL, blank=True, null=True, related_name="employees"
    )
    personnel_code = models.CharField(
        max_length=50, blank=True, null=True, unique=True, db_index=True
    )
    title = models.CharField(max_length=255, blank=True, null=True)
    hire_date = models.DateField(blank=True, null=True)

    # 👇 سه ستون مجزا
    direct_supervisor = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True,
        related_name="direct_reports"
    )
    unit_manager = models.ForeignKey(  # مدیر واحد
        User, on_delete=models.SET_NULL, blank=True, null=True,
        related_name="unit_reports"
    )
    section_head = models.ForeignKey(  # رئیس واحد
        User, on_delete=models.SET_NULL, blank=True, null=True,
        related_name="section_reports"
    )
    team_code = models.CharField(max_length=8, blank=True, default="")

    # --- ارتباط با ساختار سازمانی ---
    holding = models.ForeignKey("core.Holding", on_delete=models.PROTECT, null=True, blank=True)
    department_group = models.ForeignKey("core.DepartmentGroup", on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ["user__last_name", "user__first_name", "personnel_code"]
        verbose_name = "Employee Profile"
        verbose_name_plural = "Employee Profiles"

    @property
    def full_name(self):
        return (self.user.get_full_name() or self.user.username).strip()

    @property
    def display_label(self):
        if self.personnel_code:
            return f"{self.full_name} — {self.personnel_code}"
        return self.full_name

    def __str__(self):
        return self.display_label

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
#---------------------------------------
class ReportingLine(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="reporting_lines")
    supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_out")  # رئیس
    subordinate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_in")  # زیردست

    class Meta:
        unique_together = ("organization", "subordinate")  # هر نفر دقیقاً یک رئیس در هر سازمان
        indexes = [
            models.Index(fields=["organization", "supervisor"]),
            models.Index(fields=["organization", "subordinate"]),
        ]

    def __str__(self):
        return f"{self.organization} | {self.supervisor} → {self.subordinate}"
#---------------------------------------
class EvaluationLink(models.Model):
    class LinkType(models.TextChoices):
        DIRECT_SUPERVISOR = "DIRECT", "رئیس مستقیم"
        UNIT_MANAGER = "UNIT_MANAGER", "مدیر واحد"
        SECTION_HEAD = "SECTION_HEAD", "رئیس"
        SUPERVISOR = "SUPERVISOR", "سرپرست"
        ORG_HEAD = "ORG_HEAD", "مدیر کارخانه/سازمان"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="evaluation_links")
    evaluator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="can_evaluate")
    subordinate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="is_evaluated")
    link_type = models.CharField(max_length=20, choices=LinkType.choices)

    # --- ارتباط با ساختار سازمانی ---
    holding = models.ForeignKey("core.Holding", on_delete=models.PROTECT, null=True, blank=True)

    # برای هر نفر، از هر نوع فقط یک نفر
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "evaluator", "subordinate", "link_type"],
                name="uniq_eval_link"
            )
        ]
    def __str__(self):
        return f"{self.organization} | {self.evaluator} → {self.subordinate} [{self.link_type}]"
# ---------------------------------------
# --- فرم‌ها و معیارها ---
class FormTemplate(models.Model):
    STATUS = (("Draft","Draft"),("Published","Published"),("Archived","Archived"))
    code = models.CharField(max_length=50)                    # مثال: HR-F-84
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS, default="Draft")
    version = models.PositiveIntegerField(default=1)

    # اتصال به JobRole (اختیاری؛ اگر داری)
    applies_to_jobroles = models.ManyToManyField("JobRole", blank=True, related_name="form_template")
    # نگهداری role_levelها (مثل 901/902/...) برای انعطاف
    applies_to_role_levels = models.JSONField(blank=True, null=True)  # list[int]

    # فیلدهای نمایشی (نه الزامی)
    show_employee_signature = models.BooleanField(default=False)
    show_manager_signature  = models.BooleanField(default=False)
    show_hr_signature       = models.BooleanField(default=False)
    show_employee_comment   = models.BooleanField(default=False)
    show_next_period_goals  = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code", "-version"]
        unique_together = ("code", "version")   # نسخه‌بندی به ازای هر کد
    def __str__(self):
        return f"{self.code} v{self.version} — {self.name}"

class FormCriterion(models.Model):
    template = models.ForeignKey(FormTemplate, on_delete=models.CASCADE, related_name="criteria")
    order = models.PositiveIntegerField()
    title = models.CharField(max_length=255)        # معیار
    description = models.TextField(blank=True, default="")   # شرح معیار
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=1)

    class Meta:
        ordering = ["order"]
        unique_together = ("template", "order")

    def __str__(self):
        return f"{self.template.code}#{self.order} - {self.title}"

class FormOption(models.Model):
    criterion = models.ForeignKey(FormCriterion, on_delete=models.CASCADE, related_name="options")
    order = models.PositiveIntegerField()
    label = models.CharField(max_length=255)        # برچسب (بسیار خوب/… یا 0/2/..)
    value = models.DecimalField(max_digits=10, decimal_places=2)  # نمره (نزولی برای بهترین→بدترین)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.criterion} [{self.label}={self.value}]"

# ---------------------------------------
# --- اجرای ارزیابی و پاسخ‌ها ---

class Evaluation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        SUBMITTED = "submitted", "ارسال‌شده"

        HR_REVIEW = "hr_review", "در انتظار بررسی HR"
        MANAGER_REVIEW = "manager_review", "در انتظار بررسی مدیر"
        FACTORY_REVIEW = "factory_review", "در انتظار بررسی مدیر کارخانه"

        FINAL_APPROVED = "final_approved", "تأیید نهایی"

        APPROVED = "approved", "تأیید‌شده (قدیمی)"
        ARCHIVED = "archived", "آرشیو"
        EXPIRED = "expired", "منقضی"

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    template = models.ForeignKey('FormTemplate', on_delete=models.PROTECT, related_name='evaluations')
    template_version = models.PositiveIntegerField()

    # ارزیابی‌شونده (اسنپ‌شات سازمانی)
    employee_id = models.CharField(max_length=64)
    employee_name = models.CharField(max_length=255)
    unit_code = models.CharField(max_length=10, blank=True, default="")
    role_level = models.IntegerField(blank=True, null=True)
    team_code = models.CharField(max_length=8, blank=True, default="")

    # تا چه زمانی این Draft در لیست‌ها دیده شود
    visible_until = models.DateTimeField(null=True, blank=True)
    # اگر کاربر فقط وارد شد و هیچ آیتمی نزد هم Draft ایجاد شود
    draft_started = models.BooleanField(default=False)

    # ارزیاب/مدیر
    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='given_evaluations'
    )
    manager_id = models.CharField(max_length=64, blank=True, default="")
    manager_name = models.CharField(max_length=255, blank=True, default="")

    # زمان/دوره
    evaluated_at = models.DateField(auto_now_add=True)
    period_start = models.DateField(blank=True, null=True)
    period_end = models.DateField(blank=True, null=True)

    # فلگ‌های نمایشی (کپی از Template)
    show_employee_signature = models.BooleanField(default=False)
    show_manager_signature  = models.BooleanField(default=False)
    show_hr_signature       = models.BooleanField(default=False)
    show_employee_comment   = models.BooleanField(default=False)
    show_next_period_goals  = models.BooleanField(default=False)

    # ورودی‌های متنی/امضاها
    employee_comment = models.TextField(blank=True, default="")
    next_period_goals = models.TextField(blank=True, default="")
    employee_signed = models.BooleanField(default=False)
    manager_signed = models.BooleanField(default=False)
    hr_signed = models.BooleanField(default=False)

    # امضاهای مرحله‌ی جدید (Workflow Signature)
    factory_signed = models.BooleanField(default=False)

    hr_signed_at = models.DateTimeField(null=True, blank=True)
    manager_signed_at = models.DateTimeField(null=True, blank=True)
    factory_signed_at = models.DateTimeField(null=True, blank=True)

    # خروجی‌ها
    final_score = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_score   = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    # --- ارتباط با ساختار سازمانی ---
    holding = models.ForeignKey("core.Holding", on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'employee_id',
                    'template',
                    'template_version',
                    'period_start',
                    'period_end',
                ],
                name='unique_active_eval',
                condition=models.Q(is_archived=False),
            )
        ]

    def __str__(self):
        return f"Eval {self.employee_name} [{self.template.code} v{self.template_version}]"

    def recalc_scores(self):
        items = self.items.select_related("criterion", "selected_option").prefetch_related("criterion__options").all()
        total = 0
        max_total = 0
        for it in items:
            # اگر مقدار مستقیم ذخیره نشده، از گزینه‌ی انتخابی بگیر
            value = it.selected_value
            if value is None and it.selected_option_id:
                value = it.selected_option.value

            if value is not None:
                total += float(value) * float(it.weight or 1)

            if it.criterion and hasattr(it.criterion, "options"):
                max_opt = it.criterion.options.aggregate(models.Max("value"))["value__max"] or 0
                max_total += float(max_opt) * float(it.weight or 1)

        self.final_score = round(total, 2)
        self.max_score = round(max_total, 2)
        self.save(update_fields=["final_score", "max_score"])

    def is_complete(self):
        """
        فقط آیتم‌هایی که criterion با options دارند اجباری‌اند.
        آیتم‌های توضیحی یا بدون گزینه نمره‌دار محسوب نمی‌شوند.
        """
        items = (
            self.items
            .select_related("criterion")
            .prefetch_related("criterion__options")
        )
        required = 0
        filled = 0
        for it in items:
            has_options = it.criterion and it.criterion.options.exists()
            if not has_options:
                continue  # آیتم بدون گزینه → اجباری نیست

            required += 1

            if it.selected_option_id is not None:
                filled += 1

        return required > 0 and filled == required

    def months_label(self):
        """تعداد ماه‌ها به صورت دقیق (۳، ۶، ۹، ۱۲)"""
        if not (self.period_start and self.period_end):
            return None

        months = (
                (self.period_end.year - self.period_start.year) * 12 +
                (self.period_end.month - self.period_start.month) + 1
        )
        return months

    def submit(self):
        # بررسی کامل بودن فرم (فقط آیتم‌های نمره‌دار)
        if not self.is_complete():
            raise ValueError("همه معیارهای الزامی باید تکمیل شوند.")
        self.status = self.Status.SUBMITTED
        # ثبت زمان ارسال
        if hasattr(self, "submitted_at"):
            self.submitted_at = timezone.now()
        # ذخیره وضعیت جدید
        # اگر updated_at داری → این خط را فعال بگذار
        if hasattr(self, "updated_at"):
            self.updated_at = timezone.now()
            self.save(update_fields=["status", "submitted_at", "updated_at"])
        else:
            self.save(update_fields=["status", "submitted_at"])

    class Evaluation(models.Model):
        ...
        # بقیه فیلدها و کدهای مدل
        ...

        def advance_workflow(self, user):
            """
            انتقال فرم به مرحله بعدی گردش کار.
            """

            # DRAFT → SUBMITTED
            if self.status == self.Status.DRAFT:
                self.status = self.Status.SUBMITTED

            # SUBMITTED → HR_REVIEW
            elif self.status == self.Status.SUBMITTED:
                self.status = self.Status.HR_REVIEW

            # HR_REVIEW → MANAGER_REVIEW
            elif self.status == self.Status.HR_REVIEW:
                self.hr_signed = True
                self.hr_signed_at = timezone.now()
                self.status = self.Status.MANAGER_REVIEW

            # MANAGER_REVIEW → FACTORY_REVIEW
            elif self.status == self.Status.MANAGER_REVIEW:
                self.manager_signed = True
                self.manager_signed_at = timezone.now()
                self.status = self.Status.FACTORY_REVIEW

            # FACTORY_REVIEW → FINAL_APPROVED
            elif self.status == self.Status.FACTORY_REVIEW:
                self.factory_signed = True
                self.factory_signed_at = timezone.now()
                self.status = self.Status.FINAL_APPROVED

            self.updated_at = timezone.now()
            self.save()

        def reject_workflow(self, user):
            """
            برگشت به مرحله DRAFT برای اصلاح.
            """

            # هر Reject → برگشت کامل به DRAFT (طبق تصمیم ما)
            self.status = self.Status.DRAFT

            # پاک کردن امضاهای قبلی (خیلی مهم!)
            self.hr_signed = False
            self.manager_signed = False
            self.factory_signed = False

            self.hr_signed_at = None
            self.manager_signed_at = None
            self.factory_signed_at = None

            self.updated_at = timezone.now()
            self.save()

    def approve(self):
        """تأیید نهایی ارزیابی"""
        if self.status != self.Status.SUBMITTED:
            raise ValueError("برای تأیید، وضعیت باید Submitted باشد.")

        # محاسبه مجدد امتیاز از آیتم‌های ارزیابی
        try:
            self.recalc_scores()
        except Exception as ex:
            print(f"⚠️ خطا در محاسبه امتیاز هنگام تأیید: {ex}")

        # تغییر وضعیت و زمان
        self.status = self.Status.APPROVED
        self.approved_at = timezone.now()

        # ذخیره تمام تغییرات شامل امتیاز نهایی
        self.save(update_fields=["status", "approved_at", "final_score", "max_score", "updated_at"])

    def ensure_visible_until(self):
        """
        مهلت پیش‌نویس‌ها را همیشه 1 ماه بعد از زمان فعلی تنظیم می‌کند.
        اگر visible_until گذشته باشد، مجدداً یک ماه مهلت داده می‌شود.
        """
        from django.utils import timezone
        from dateutil.relativedelta import relativedelta

        now = timezone.now()

        # همیشه 1 ماه مهلت جدید بده
        self.visible_until = now + relativedelta(months=1)

    @property
    def has_progress(self):
        return self.items.filter(selected_option__isnull=False).exists()

    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)

    def archive_if_expired(self):
        from django.utils import timezone
        if self.status == self.Status.DRAFT and self.visible_until and self.visible_until < timezone.now():
            self.is_archived = True
            # (اختیاری) اگر status اضافه کنی: self.status = "expired"
            self.archived_at = timezone.now()
            self.save(update_fields=["is_archived", "archived_at"])  # + ["status"] اگر داری

    @property
    def period_label(self):
        m = self.months_label()
        if not m:
            return "بدون بازه"
        if m in [3, 6, 9, 12]:
            return f"{m} ماهه"
        return f"{m} ماهه (غیراستاندارد)"

class EvaluationItem(models.Model):
    evaluation = models.ForeignKey('Evaluation', on_delete=models.CASCADE, related_name='items')
    # اسنپ‌شات معیار
    criterion = models.ForeignKey('FormCriterion', on_delete=models.SET_NULL, null=True, blank=True)
    criterion_order = models.PositiveIntegerField()
    criterion_title = models.CharField(max_length=255)
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=1)

    # انتخاب و امتیاز
    selected_option = models.ForeignKey('FormOption', on_delete=models.SET_NULL, null=True, blank=True)
    selected_label = models.CharField(max_length=255, blank=True, default="")
    selected_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    earned_points = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    comment = models.TextField(blank=True, default="")

    class Meta:
        ordering = ['criterion_order']

    def __str__(self):
        return f"{self.evaluation} #{self.criterion_order}"

    def apply_selection(self, option):
        self.selected_option = option
        self.selected_label = option.label
        self.selected_value = option.value
        self.earned_points = round(float(option.value) * float(self.weight or 1), 2)
        self.save()
        self.evaluation.recalc_scores()
#-------------------------------------------------------------------

class EvaluationSignature(models.Model):
    ROLE_MANAGER = "manager"
    ROLE_HR = "hr"
    ROLE_FACTORY = "factory"

    ROLE_CHOICES = [
        (ROLE_MANAGER, "Manager"),
        (ROLE_HR, "HR"),
        (ROLE_FACTORY, "Factory Manager"),
    ]

    evaluation = models.ForeignKey(
        "Evaluation",
        on_delete=models.CASCADE,
        related_name="signatures"
    )

    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES
    )

    signed_at = models.DateTimeField(auto_now_add=True)

    comment = models.TextField(blank=True)

    is_final = models.BooleanField(default=False)

    signed_by_name = models.CharField(max_length=150, null=True, blank=True)
    signed_by_personnel_code = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        unique_together = ("evaluation", "role")
        ordering = ["signed_at"]

    def __str__(self):
        return f"Evaluation {self.evaluation_id} - {self.role}"
