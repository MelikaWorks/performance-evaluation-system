# core/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django import forms
from django.db.models import Min, Q
from django.core.exceptions import ValidationError
from django.utils.html import escape
from django.utils.safestring import mark_safe
from uuid import uuid4
from django_select2.forms import Select2Widget
from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from core.admin_filters import OrganizationQuickFilter
from core.models import (
    Organization,
    Unit,
    JobRole,
    EmployeeProfile,
    ReportingLine,
    EvaluationLink,
    FormTemplate,
    FormCriterion,
    FormOption,
)

# فرم‌های اختصاصی
from core.forms.core_forms import UserCreationWithProfileForm
# 💎 ثابت‌ها و تنظیمات مرکزی
from core.constants import Settings

# ==========branding====================================
class EvalAdminSite(AdminSite):
    site_header = "سامانه ارزیابی عملکرد سازمانی"
    site_title = "سامانه ارزیابی عملکرد سازمانی"
    index_title = "داشبورد مدیریت"

custom_admin_site = EvalAdminSite(name="eval_admin")
User = get_user_model()
# =========================================================
class DatalistInput(forms.TextInput):
    """
    TextInput + <datalist> برای پیشنهادهای سرچ‌شونده (بدون تغییر مدل).
    """

    def __init__(self, options=None, attrs=None):
        super().__init__(attrs)
        self.options = [o for o in (options or []) if (o or "").strip()]
        self.list_id = f"id_titles_{uuid4().hex[:8]}"

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        attrs["list"] = self.list_id
        input_html = super().render(name, value, attrs, renderer)
        opts = "".join(f"<option value=\"{escape(opt)}\"></option>" for opt in self.options)
        datalist_html = f"<datalist id=\"{self.list_id}\">{opts}</datalist>"
        return mark_safe(input_html + datalist_html)

# ----------------------------------
def get_org_head_user_id(org_id: int | None):
    """
    اول از ReportingLine بخوان: هر supervisor که JobRole=900 در همین سازمان دارد.
    اگر نبود یا org_id نداشتیم، fallback به Settings.ORG_HEAD_PCODE.
    """
    from core.models import EmployeeProfile, ReportingLine

    if org_id:
        sup_ids = (EmployeeProfile.objects
                   .filter(organization_id=org_id,job_role__code=Settings.ROLE_FACTORY_MANAGER,user__isnull=False)
                   .values_list("user_id", flat=True))
        head_uid = (ReportingLine.objects
                    .filter(organization_id=org_id, supervisor_id__in=sup_ids)
                    .values_list("supervisor_id", flat=True).first())
        if head_uid:
            return head_uid

    # fallback از کد پرسنلی
    return (EmployeeProfile.objects
            .filter(personnel_code=Settings.ORG_HEAD_PCODE, user__isnull=False)
            .values_list("user_id", flat=True).first())

# -------------------------------
def user_display(u: User) -> str:
    """نمایش حیوزر به صورت: نام کامل — کُد پرسنلی (اگر داشته باشد)."""
    if not u:
        return "-"
    full_name = (u.get_full_name() or u.username).strip()
    try:
        pcode = getattr(u.employee_profile, "personnel_code", None)
    except Exception:
        pcode = None
    return f"{full_name} — {pcode}" if pcode else full_name

# ----------------------------------
def get_user_by_jobrole_name(org_id, role_name):
    """اولین کاربری که در این سازمان نقش مورد نظر را دارد (و user خالی نیست)"""
    ep = (EmployeeProfile.objects
          .filter(organization_id=org_id, user__isnull=False, job_role__name__icontains=role_name)
          .select_related("user")
          .first())
    return getattr(ep, "user", None)

# ----------------------------------
# برچسب نتایج اتوکامپلیتِ User (کُد — نام)
# (فقط داخل ادمین اثر دارد)
# -----------------------------------
def _user_str(self):
    try:
        p = self.employee_profile
        pcode = (p.personnel_code or "").strip()
    except EmployeeProfile.DoesNotExist:
        pcode = ""
    full_name = (self.get_full_name() or self.username).strip()
    return f"{pcode} — {full_name}" if pcode else full_name

User.__str__ = _user_str

# -----------------------------------
# Organization
# -----------------------------------
@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)

# ------------------------------------
# Unit Admin Form
# -------------------------------
class UnitAdminForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        has_manager = "manager" in self.fields
        has_parent = "parent_unit" in self.fields

        # نمایش «کد پرسنلی — نام» برای کاربران
        def _user_label(u):
            try:
                pcode = (u.employee_profile.personnel_code or "").strip()
            except EmployeeProfile.DoesNotExist:
                pcode = ""
            fullname = (u.get_full_name() or u.username).strip()
            return f"{pcode} — {fullname}" if pcode else fullname

        if has_manager:
            self.fields["manager"].label_from_instance = _user_label
        if has_parent:
            self.fields["parent_unit"].label_from_instance = (
                lambda u: f"{u.name} — {u.unit_code or ''}"
            )

        org_id = getattr(self.instance, "organization_id", None) or self.initial.get("organization")
        creating = not getattr(self.instance, "pk", None)

        # حالت Add → فقط مدیران کلی (۹۰۰ و ۹۰۱)
        if creating:
            if has_manager:
                ep = EmployeeProfile.objects.filter(job_role__code__in=["900", "901"], user__isnull=False)
                if org_id:
                    ep = ep.filter(organization_id=org_id)
                self.fields["manager"].queryset = (
                    User.objects.filter(id__in=ep.values_list("user_id", flat=True))
                    .order_by("last_name", "first_name", "username").distinct()
                )
            return

        # حالت Edit
        if not has_manager:
            return

        u = self.instance
        unit_code = (u.unit_code or "").strip()
        unit_name = (u.name or "").strip()
        allow_900 = (unit_code in Settings.ALLOW_900_MANAGER_CODES) or (unit_name in Settings.ALLOW_900_MANAGER_NAMES)

        base = EmployeeProfile.objects.filter(user__isnull=False)
        if org_id:
            base = base.filter(organization_id=org_id)

        if allow_900:
            ep = base.filter(Q(job_role__code="900") | (Q(job_role__code="901") & Q(unit_id=u.id)))
        else:
            ep = base.filter(job_role__code="901", unit_id=u.id)

        # === استثناء: واحدهایی که مدیرشان باید از جای دیگر بیاید ===
        # EXTERNAL_MANAGER_SOURCE = {
        #     "230": "114",  # تدارکات → مدیر برنامه‌ریزی و سیستم‌ها
        # }
        src_code = Settings.EXTERNAL_MANAGER_SOURCE.get(unit_code)
        if src_code:
            src_unit = Unit.objects.filter(organization_id=org_id, unit_code=src_code).first()
            if src_unit:
                extra = base.filter(job_role__code="901", unit_id=src_unit.id)
                ep = ep.union(extra)

        self.fields["manager"].queryset = (
            User.objects.filter(id__in=ep.values_list("user_id", flat=True))
            .order_by("last_name", "first_name", "username").distinct()
        )

        # دیفالت برای مالی/حراست (اگر خالی باشد) → مدیر کارخانه
        if (not u.manager) and (unit_code in (Settings.FINANCE_UNIT_CODES | Settings.SECURITY_UNIT_CODES)):
            head_uid = get_org_head_user_id(org_id)
            if head_uid:
                self.fields["manager"].initial = head_uid

    def clean_manager(self):
        mgr = self.cleaned_data.get("manager")
        if not mgr:
            return mgr

        # پروفایل مدیر انتخابی
        try:
            ep_mgr = mgr.employee_profile
        except EmployeeProfile.DoesNotExist:
            raise ValidationError("کاربر انتخاب‌شده پروفایل پرسنلی ندارد.")

        # تشخیص وضعیت: ایجاد یا ویرایش
        creating = not getattr(self.instance, "pk", None)

        # استخراج organization و unit_code برای هر دو حالت
        if creating:
            org_id = self.cleaned_data.get("organization") or self.initial.get("organization")
            unit_code = (self.cleaned_data.get("unit_code") or "").strip()
        else:
            org_id = getattr(self.instance, "organization_id", None)
            unit_code = (getattr(self.instance, "unit_code", "") or "").strip()

        is_logistics = unit_code in Settings.LOGISTICS_UNIT_CODES

        # نقش مجاز
        role_code = getattr(getattr(ep_mgr, "job_role", None), "code", None)
        if role_code not in (["900", "901"] if is_logistics else ["901"]):
            raise ValidationError("فقط کاربران با نقش مدیریتی (۹۰۰/۹۰۱) قابل انتخاب هستند.")

        # در حالت غیر لجستیک: باید یا مدیر همان واحد باشد
        # یا در استثناءِ «مدیر از واحدِ منبع» قرار بگیرد.
        if not is_logistics:
            # واحدِ فعلی (در ویرایش) یا واحد منطبق با داده‌های فرم (در ایجاد)
            current_unit_id = getattr(self.instance, "id", None)

            same_unit = (current_unit_id is not None and ep_mgr.unit_id == current_unit_id)

            # استثناء: مدیر از واحدِ منبع
            src_code = Settings.EXTERNAL_MANAGER_SOURCE.get(unit_code)
            from_source_unit = bool(
                src_code and getattr(ep_mgr.unit, "unit_code", None) == src_code
            )

            if not (same_unit or from_source_unit):
                raise ValidationError("برای این واحد فقط مدیر همان واحد یا واحدِ منبعِ مجاز قابل انتخاب است.")

        return mgr

# -------------------------------
# Unit
# -------------------------------
@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    form = UnitAdminForm
    autocomplete_fields = ("manager", "parent_unit")
    exclude = ("supervision_policy",)
    list_display = ("unit_code", "name", "organization", "manager_label")
    list_filter = ("organization",)
    search_fields = ("name", "unit_code", "manager__first_name", "manager__last_name", "manager__username")
    actions = ["apply_parent_mapping", "apply_manager_mapping", "clear_no_manager_units"]

    # فقط در صفحه‌ی Add این 3 فیلد را نشان بده
    def get_fields(self, request, obj=None):
        if obj is None:  # add view
            return ("organization", "name", "parent_unit", "manager", "unit_code")
        return ("organization", "name", "parent_unit", "manager", "unit_code")  # 👈 بدون head

    def get_fieldsets(self, request, obj=None):
        fields = self.get_fields(request, obj)
        return ((None, {"fields": fields}),)

    def save_model(self, request, obj, form, change):
        code = (obj.unit_code or "").strip()

        # 1) مالی/حراست → اگر خالی بود، مدیر کارخانه
        if (not obj.manager) and (
                code in (Settings.FINANCE_UNIT_CODES | Settings.SECURITY_UNIT_CODES)
        ):
            head_uid = get_org_head_user_id(obj.organization_id)
            if head_uid:
                obj.manager_id = head_uid

        # 2) استثناء: مدیر از واحدِ منبع
        if not obj.manager:
            src_code = Settings.EXTERNAL_MANAGER_SOURCE.get(code)
            if src_code:
                src_unit = Unit.objects.filter(
                    organization_id=obj.organization_id, unit_code=src_code
                ).first()
                if src_unit:
                    ep = (EmployeeProfile.objects
                          .filter(organization_id=obj.organization_id,
                                  unit_id=src_unit.id,
                                  job_role__code="901",
                                  user__isnull=False)
                          .select_related("user")
                          .first())
                    if ep and ep.user:
                        obj.manager = ep.user

        # 3) Parent unit خالی → «مدیریت» همان سازمان
        if not obj.parent_unit_id and obj.organization_id:
            parent = Unit.objects.filter(
                organization_id=obj.organization_id, name=Settings.DEFAULT_PARENT_NAME
            ).first()
            if parent:
                obj.parent_unit = parent

        super().save_model(request, obj, form, change)

    @admin.display(description="Manager")
    def manager_label(self, obj):
        u = obj.manager
        if not u:
            return "—"
        try:
            pc = (u.employee_profile.personnel_code or "").strip()
        except EmployeeProfile.DoesNotExist:
            pc = ""
        nm = (u.get_full_name() or u.username).strip()
        return f"{pc} — {nm}" if pc else nm

    def get_search_results(self, request, queryset, search_term):
        qs, use_distinct = super().get_search_results(request, queryset, search_term)

        # فقط اتوکامپلیتِ فیلد manager را محدود کن
        if request.path.endswith("/autocomplete/"):
            if (request.GET.get("app_label") == "js"
                    and request.GET.get("model_name") == "unit"
                    and request.GET.get("field_name") == "manager"):
                allowed = (EmployeeProfile.objects
                           .filter(job_role__code__in=["900", "901"], user__isnull=False)
                           .values_list("user_id", flat=True))
                qs = qs.filter(id__in=allowed)

        return qs, use_distinct

    @admin.display(description="Head")
    def head_label(self, obj):
        u = obj.head
        if not u: return "—"
        try:
            pc = (u.employee_profile.personnel_code or "").strip()
        except EmployeeProfile.DoesNotExist:
            pc = ""
        nm = (u.get_full_name() or u.username).strip()
        return f"{pc} — {nm}" if pc else nm

    @admin.action(description="Clear managers for units that should NOT have their own manager")
    def clear_no_manager_units(self, request, queryset):
        updated = 0
        for unit in queryset:
            code = (getattr(unit, "unit_code", "") or "").strip()
            name = (getattr(unit, "name", "") or "").strip()
            allow_900 = (
                    code in Settings.ALLOW_900_MANAGER_CODES
                    or name in Settings.ALLOW_900_MANAGER_NAMES
            )
            if not allow_900 and unit.manager_id:
                unit.manager = None
                unit.save(update_fields=["manager"])
                updated += 1
        self.message_user(request, f"Managers cleared: {updated}")

    @admin.action(description="Set unit manager by mapping (unit_code → personnel_code)")
    def apply_manager_mapping(self, request, queryset):
        MANAGER_MAP = {
            # مثال: "219": "220001",
        }
        updated = 0
        for unit in queryset:
            code = (getattr(unit, "unit_code", None) or "").strip()
            pcode = MANAGER_MAP.get(code)
            if not pcode:
                continue
            try:
                u = User.objects.get(username=pcode)
            except User.DoesNotExist:
                continue
            if unit.manager_id != u.id:
                unit.manager = u
                unit.save(update_fields=["manager"])
                updated += 1
        self.message_user(request, f"Managers updated: {updated}")

# -------------------------------
# JobRole
# -------------------------------
@admin.register(JobRole)
class JobRoleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "organization_name",     # ✅ جایگزین صحیح
        "units_codes_col",
        "is_active",
    )

    list_filter = (
        "organization__name",    # ✅ اینجا مجازه
        "is_active",
    )

    search_fields = (
        "name",
        "code",
        "allowed_units__unit_code__exact",
        "allowed_units__name",
        "organization__name",    # ✅ اینجا هم مجازه
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return (
            qs
            .select_related("organization")   # 👈 خیلی مهم
            .prefetch_related("allowed_units")
            .annotate(min_unit_code=Min("allowed_units__unit_code"))
            .order_by("min_unit_code", "name")
        )

    @admin.display(description="Organization", ordering="organization__name")
    def organization_name(self, obj):
        return obj.organization.name if obj.organization else "—"

    @admin.display(description="UNITS (CODES)", ordering="min_unit_code")
    def units_codes_col(self, obj: JobRole):
        codes = [
            (u.unit_code or "").strip()
            for u in obj.allowed_units.all()
            if (u.unit_code or "").strip()
        ]
        if not codes:
            return "—"
        uniq = sorted(set(codes), key=lambda x: (len(x), x))
        return ", ".join(uniq)

# ==========================================================
# EmployeeProfile ***
# ==========================================================
class EmployeeProfileAdminForm(forms.ModelForm):
    class Meta:
        model = EmployeeProfile
        fields = "__all__"

    class Media:
        js = (
            "admin/js/vendor/jquery/jquery.js",
            "admin/js/jquery.init.js",
            "js/employeeprofile_ajax.js",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # --- Dropdown برای Title ---
        # titles_qs = EmployeeProfile.objects.order_by().values_list("title", flat=True).distinct()
        # roles_qs = JobRole.objects.order_by().values_list("name", flat=True).distinct()
        #
        # merged = sorted(set([t for t in titles_qs if t] + [r for r in roles_qs if r]))
        #
        # cur = (self.instance.title or "").strip() if getattr(self, "instance", None) else ""
        # if cur and cur not in merged:
        #     merged = [cur] + merged

        cur = (self.instance.title or "").strip() if getattr(self, "instance", None) else ""

        self.fields["title"] = forms.ChoiceField(
            choices=[("", "— انتخاب کنید —")] + ([(cur, cur)] if cur else []),
            required=False,
            label="عنوان شغلی",
            widget=Select2Widget(attrs={
                "style": "width: 28rem; max-width: 100%;",
                "dir": "rtl",
                "data-placeholder": "— انتخاب کنید —",
            }),
        )

        # فقط نام یونیت را نشان بده
        if "unit" in self.fields:
            self.fields["unit"].label_from_instance = lambda un: un.name

        # لیبل خوش‌خوان برای یوزرها: "نام کامل — کُد پرسنلی"
        def user_label(u: User):
            full = (u.get_full_name() or u.username).strip()
            try:
                pcode = getattr(u.employee_profile, "personnel_code", "")
            except Exception:
                pcode = ""
            return f"{full} — {pcode}" if pcode else full

        for fname in ("direct_supervisor", "section_head", "unit_manager"):
            if fname in self.fields:
                self.fields[fname].label_from_instance = user_label

        # در حالت ادیت، این‌ها را قفل کن
        if self.instance and self.instance.pk:
            for f in ("user", "personnel_code"):
                if f in self.fields:
                    self.fields[f].disabled = True

        if "direct_supervisor" in self.fields:
            self.fields[
                "direct_supervisor"].help_text = "بعد از تغییر «واحد»، یک‌بار «ذخیره و ادامهٔ ویرایش» بزنید تا لیست مدیر به‌روز شود."
        if "section_head" in self.fields:
            self.fields[
                "section_head"].help_text = "بعد از تغییر «واحد»، یک‌بار «ذخیره و ادامهٔ ویرایش» بزنید تا لیست رئیس به‌روز شود."
        if "unit_manager" in self.fields:
            self.fields[
                "unit_manager"].help_text = "بعد از تغییر «واحد»، یک‌بار «ذخیره و ادامهٔ ویرایش» بزنید تا لیست مدیر به‌روز شود."

# ----------------------------------
@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    form = EmployeeProfileAdminForm

    class Media:
        js = (
            "admin/js/vendor/jquery/jquery.js",
            "admin/js/jquery.init.js",
            "js/employeeprofile_ajax.js",
        )

    # (هیچ Media/JS لازم نیست)
    list_display = (
        "display_label", "personnel_code_col", "organization",
        "unit_name_only", "unit_code", "job_role", "title",
        "manager_col", "head_col",
    )
    list_select_related = ("user", "unit", "job_role", "organization")
    list_filter = (OrganizationQuickFilter, "unit", "job_role")
    list_per_page = 50
    ordering = ("user__last_name", "user__first_name", "personnel_code")
    search_fields = (
        "personnel_code",
        "user__first_name", "user__last_name", "user__username", "user__email",
        "unit__name", "unit__unit_code",
        "job_role__name", "organization__name", "title",
    )
    readonly_fields = ("user", "personnel_code", "unit_code")
    fields = (
        "organization",
        "unit",
        "job_role",
        "title",  # همان فیلدی که اکنون Datalist شده
        "hire_date",
        "direct_supervisor",
        "section_head",
    )

    autocomplete_fields = ( "unit", "organization", "user")

    def get_fields(self, request, obj=None):
        fields = [
            "user", "organization", "unit", "unit_code",
            "job_role", "personnel_code", "title", "hire_date",
            "direct_supervisor",  # مدیر (901 | لجستیک: 900)
            "section_head",  # رئیس (902)
        ]
        if obj:
            fields.remove("user")
            fields.remove("personnel_code")
        return fields

    # ------ ستون‌های نمایشی ------
    @admin.display(description="برچسب")
    def display_label(self, obj):
        u = getattr(obj, "user", None)
        full = (u.get_full_name() if u else "") or (u.username if u else "")
        code = obj.personnel_code or ""
        return f"{full} — {code}" if code else (full or "—")

    @admin.display(description="کُد پرسنلی")
    def personnel_code_col(self, obj):
        return obj.personnel_code or "—"

    @admin.display(description="UNIT")
    def unit_name_only(self, obj):
        return obj.unit.name if obj.unit else "—"

    @admin.display(description="Unit code")
    def unit_code(self, obj):
        return (getattr(getattr(obj, "unit", None), "unit_code", "") or "—")

    @admin.display(description="مدیر")
    def manager_col(self, obj):
        # obj: معمولاً EmployeeProfile یا آبجکت مشابه که unit و organization دارد
        u = getattr(obj, "unit", None)
        if not u:
            return "—"

        unit_code = (str(getattr(u, "unit_code", "")).strip() or "")
        unit_name = (getattr(u, "name", "") or "").strip()

        # 1) اگر خود یونیت مدیر دارد → همان
        if getattr(u, "manager", None):
            mgr = u.manager
            return (mgr.get_full_name() or mgr.username) if mgr else "—"

        # 2) اگر یونیت جزو مجموعه‌هایی است که 900 می‌تواند مدیرشان باشد → مدیر کارخانه
        if (
                unit_code in Settings.ALLOW_900_MANAGER_CODES
                or unit_name in Settings.ALLOW_900_MANAGER_NAMES
        ):
            if Settings.ORG_HEAD_PCODE:
                try:
                    head_ep = EmployeeProfile.objects.get(
                        personnel_code=Settings.ORG_HEAD_PCODE,
                        organization=obj.organization
                    )
                    head_user = head_ep.user
                    return (head_user.get_full_name() or head_user.username) if head_user else "—"
                except EmployeeProfile.DoesNotExist:
                    pass

        # 3) در غیر این صورت چیزی نداریم
        return "—"

    @admin.display(description="رئیس")
    def head_col(self, obj: EmployeeProfile):
        u = getattr(obj, "unit", None)
        if not u:
            return "—"

        unit_code = (str(getattr(u, "unit_code", "")).strip() or "")
        unit_name = (getattr(u, "name", "") or "").strip()

        # 1) اگر برای خود رکورد section_head ست شده
        if getattr(obj, "section_head", None):
            sh = obj.section_head
            return (sh.get_full_name() or sh.username) if sh else "—"

        # 2) برای لجستیک و مدیریت → رئیس = مدیر کارخانه
        if (unit_code in Settings.LOGISTICS_UNIT_CODES) or (unit_code in Settings.HEAD_UNIT_CODES) or (unit_name == "مدیریت"):
            if Settings.ORG_HEAD_PCODE:
                from core.models import EmployeeProfile as EP
                try:
                    head_ep = EP.objects.get(personnel_code=Settings.ORG_HEAD_PCODE, organization=obj.organization)
                    head_user = head_ep.user
                    return (head_user.get_full_name() or head_user.username) if head_user else "—"
                except EP.DoesNotExist:
                    pass

        # 3) اگر یونیت مدیر ندارد ولی direct_supervisor داریم → همان
        if not getattr(u, "manager", None) and getattr(obj, "direct_supervisor", None):
            ds = obj.direct_supervisor
            return (ds.get_full_name() or ds.username) if ds else "—"

        # 4) اگر direct_supervisor ست است و با مدیر یونیت فرق دارد → همان
        if getattr(obj, "direct_supervisor", None) and getattr(u, "manager", None):
            if obj.direct_supervisor_id != u.manager_id:
                ds = obj.direct_supervisor
                return (ds.get_full_name() or ds.username) if ds else "—"

        return "—"

    # ------ اتصال obj به request برای استفاده داخل formfield_for_foreignkey ------
    def get_form(self, request, obj=None, **kwargs):
        self._current_obj = obj  # برای دسترسی به unit فعلی
        return super().get_form(request, obj, **kwargs)

    # ------ نرمال‌سازی ارقام ------
    @staticmethod
    def _norm_digits(s):
        fa = "۰۱۲۳۴۵۶۷۸۹";
        ar = "٠١٢٣٤٥٦٧٨٩"
        return str(s).translate(str.maketrans(fa + ar, "0123456789" * 2)).strip()

    # ------ فیلترینگ سمت سرور برای مدیر/رئیس ------
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in {"direct_supervisor", "section_head", "unit_manager"}:
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

# -------------------------------
# Custom User Admin (ساخت کاربر + پروفایل Inline)
# -------------------------------
class EmployeeProfileInline(admin.StackedInline):
    model = EmployeeProfile
    form = EmployeeProfileAdminForm
    can_delete = False
    fk_name = "user"
    extra = 0
    fields = (
        "organization",
        "unit",
        "job_role",
        "title",
        "hire_date",
        "direct_supervisor",
        "section_head",
    )
    autocomplete_fields = ("unit", "job_role", "direct_supervisor", "section_head")

class CustomUserAdmin(BaseUserAdmin):
    add_form = UserCreationWithProfileForm
    # صفحه "Add user"
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'first_name', 'last_name', 'email',
                'password1', 'password2',
                'personnel_code',
            ),
        }),
    )
    list_filter = (
        OrganizationQuickFilter,  # ← فیلتر چند سازمانی
        "is_staff",
        "is_superuser",
        "is_active",
    )
    inlines = (EmployeeProfileInline,)
    list_display = ("username", "first_name", "last_name", "email", "is_staff", "is_active")
    search_fields = (
        "username", "first_name", "last_name", "email",
        "employee_profile__personnel_code",
    )

    def save_model(self, request, obj, form, change):
        # قبل از ذخیرهٔ User، یوزرنیم را از فیلد «کد پرسنلی» پر کن
        pcode = form.cleaned_data.get("personnel_code")
        if pcode:
            obj.username = pcode
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        # userِ تازه‌ساخته‌شده:
        user_obj = form.instance  # بعد از save_model مقدار دارد
        pcode = form.cleaned_data.get("personnel_code") or getattr(user_obj, "username", "")
        for inst in instances:
            # اگر این اینلاین مربوط به پروفایل است و کد پرسنلی هنوز خالی‌ست، پرش کن
            if isinstance(inst, EmployeeProfile) and not (inst.personnel_code or "").strip():
                inst.personnel_code = pcode
            # مطمئن شو FK ست است
            inst.user = user_obj
            inst.save()
        formset.save_m2m()

    def get_search_results(self, request, queryset, search_term):
        qs, use_distinct = super().get_search_results(request, queryset, search_term)

        if request.path.endswith("/autocomplete/"):
            app = request.GET.get("app_label")
            model = request.GET.get("model_name")
            field = request.GET.get("field_name")

            # Unit.manager → فقط مدیرها (900/901)
            if app == "js" and model == "unit" and field == "manager":
                allowed = (EmployeeProfile.objects
                           .filter(job_role__code__in=[Settings.ROLE_MANAGER, Settings.ROLE_UNIT_MANAGER], user__isnull=False)
                           .values_list("user_id", flat=True))
                qs = qs.filter(id__in=allowed)

            # ReportingLine.supervisor → فقط مدیرها (900/901)
            elif app == "js" and model == "reportingline" and field == "supervisor":
                allowed = (EmployeeProfile.objects
                           .filter(job_role__code__in=[Settings.ROLE_MANAGER, Settings.ROLE_UNIT_MANAGER], user__isnull=False)
                           .values_list("user_id", flat=True))
                qs = qs.filter(id__in=allowed)

            # ReportingLine.subordinate → همه‌ی پرسنل (هر کسی EmployeeProfile دارد)
            elif app == "js" and model == "reportingline" and field == "subordinate":
                allowed = (EmployeeProfile.objects
                           .filter(user__isnull=False)
                           .values_list("user_id", flat=True))
                qs = qs.filter(id__in=allowed)

        return qs, use_distinct

# ثبت مجدد User با ادمین سفارشی
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# -------------------------------
# ReportingLine
# -------------------------------
class ReportingLineAdminForm(forms.ModelForm):
    class Meta:
        model = ReportingLine
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # لیبل‌ها: «کُد — نام»
        self.fields["supervisor"].label_from_instance = user_display
        self.fields["subordinate"].label_from_instance = user_display

        org_id = getattr(self.instance, "organization_id", None) or self.initial.get("organization")

        # فقط مدیرها (900/901) برای Supervisor
        sup_ep = EmployeeProfile.objects.filter(
            job_role__code__in=[Settings.ROLE_FACTORY_MANAGER, Settings.ROLE_UNIT_MANAGER], user__isnull=False
        )
        if org_id:
            sup_ep = sup_ep.filter(organization_id=org_id)

        self.fields["supervisor"].queryset = (
            User.objects.filter(id__in=sup_ep.values_list("user_id", flat=True))
            .order_by("last_name", "first_name", "username")
            .distinct()
        )

        # همهٔ پرسنل برای Subordinate
        sub_ep = EmployeeProfile.objects.filter(user__isnull=False)
        if org_id:
            sub_ep = sub_ep.filter(organization_id=org_id)

        self.fields["subordinate"].queryset = (
            User.objects.filter(id__in=sub_ep.values_list("user_id", flat=True))
            .order_by("last_name", "first_name", "username")
            .distinct()
        )

    def clean(self):
        cleaned = super().clean()
        sup = cleaned.get("supervisor")
        sub = cleaned.get("subordinate")
        if sup and sub and sup.id == sub.id:
            raise ValidationError("سرپرست و زیردست نمی‌توانند یک نفر باشند.")

        org_id = cleaned.get("organization").id if cleaned.get("organization") else None
        for who, label in [(sup, "سرپرست"), (sub, "زیردست")]:
            if not who:
                continue
            ep = getattr(who, "employee_profile", None)
            if ep and ep.organization_id and org_id and ep.organization_id != org_id:
                raise ValidationError(f"سازمان {label} با Organization رکورد هم‌خوان نیست.")
        return cleaned

@admin.register(ReportingLine)
class ReportingLineAdmin(admin.ModelAdmin):
    form = ReportingLineAdminForm
    autocomplete_fields = ("supervisor", "subordinate")
    list_display = ("organization", "supervisor_label", "subordinate_label")
    list_filter = ("organization",)
    search_fields = (
        "supervisor__username", "supervisor__first_name", "supervisor__last_name",
        "supervisor__employee_profile__personnel_code",
        "subordinate__username", "subordinate__first_name", "subordinate__last_name",
        "subordinate__employee_profile__personnel_code",
    )

    @admin.display(description="سرپرست")
    def supervisor_label(self, obj: ReportingLine):
        return user_display(obj.supervisor)

    @admin.display(description="زیردست")
    def subordinate_label(self, obj: ReportingLine):
        return user_display(obj.subordinate)

        # اختیاری: اعتبارسنجی ساده در ادمین

    def save_model(self, request, obj, form, change):
        if obj.supervisor_id == obj.subordinate_id:
            from django.core.exceptions import ValidationError
            raise ValidationError("سرپرست و زیردست نمی‌توانند یک نفر باشند.")
        # هردو باید در همان organization باشند (اگر پروفایل دارند)
        for u in (obj.supervisor, obj.subordinate):
            ep = getattr(u, "employee_profile", None)
            if ep and ep.organization_id and obj.organization_id and ep.organization_id != obj.organization_id:
                from django.core.exceptions import ValidationError
                raise ValidationError("سازمان سرپرست/زیردست با Organization رکورد هم‌خوان نیست.")
        super().save_model(request, obj, form, change)

# -------------------------------
# EvaluationLink
# -------------------------------
@admin.register(EvaluationLink)
class EvaluationLinkAdmin(admin.ModelAdmin):

    # پنهان از منو
    def has_module_permission(self, request):
        return False

    # بستن هرگونه دسترسی مستقیم
    def has_view_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

# -------------------------------
# Evaluation Form
# -------------------------------
class FormOptionInline(admin.TabularInline):
    model = FormOption
    extra = 0

class FormCriterionInline(admin.TabularInline):
    model = FormCriterion
    extra = 0

@admin.register(FormTemplate)
class FormTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "version", "updated_at")
    list_filter = ("status",)
    search_fields = ("code", "name")
    filter_horizontal = ("applies_to_jobroles",)
    inlines = [FormCriterionInline]

@admin.register(FormCriterion)
class FormCriterionAdmin(admin.ModelAdmin):
    list_display = ("template", "order", "title", "weight")
    inlines = [FormOptionInline]

@admin.register(FormOption)
class FormOptionAdmin(admin.ModelAdmin):
    list_display = ("criterion", "order", "label", "value")

# ==========================Report===========================
# یک Proxy Model صرفاً برای داشتن یک منو در ادمین

# رجیستر را به گزارش‌ها می‌سپاریم views/admin/reports.py)
# اینجا فقط import می‌کنیم تا load شود:
from core.views.admin.reports import EvaluationReport, EvaluationReportAdmin

admin.site.register(EvaluationReport, EvaluationReportAdmin)
