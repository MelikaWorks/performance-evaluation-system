from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from core.models import JobRole, EmployeeProfile
from django.utils.html import escape
from django.utils.safestring import mark_safe
from uuid import uuid4
import re

def user_display_label(u: User) -> str:
    """تولید برچسب: نام — کد پرسنلی"""
    full_name = (u.get_full_name() or u.username).strip()
    try:
        pcode = getattr(u.employee_profile, "personnel_code", None)
    except Exception:
        pcode = None
    return f"{full_name} — {pcode}" if pcode else full_name

class UserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return user_display_label(obj)

class UserCreationWithProfileForm(UserCreationForm):
    """
    فرم ساخت یوزر سفارشی برای Admin:
    - همراه با انتخاب سازمان، واحد، سمت و سایر مشخصات پروفایل کارمند
    """
    personnel_code = forms.CharField(max_length=50, required=True, label="کد پرسنلی")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "first_name", "last_name", "email",
            "password1", "password2","personnel_code",
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["personnel_code"]
        if commit:
            user.save()
            # پروفایل کارمند بساز یا آپدیت کن
            EmployeeProfile.objects.update_or_create(
                user=user,
                defaults={
                    "personnel_code": self.cleaned_data["personnel_code"],
                }
            )
        return user

    def clean_personnel_code(self):
        code = (self.cleaned_data.get("personnel_code") or "").strip()

        # اگر خالی بود، خطا بده
        if not code:
            raise forms.ValidationError("کد پرسنلی الزامی است.")

        # اگر فقط عدد نبود (حتی اعداد فارسی یا عربی را هم نرمال می‌کنیم)
        import re
        # تبدیل اعداد فارسی و عربی به انگلیسی
        fa = "۰۱۲۳۴۵۶۷۸۹"
        ar = "٠١٢٣٤٥٦٧٨٩"
        code = code.translate(str.maketrans(fa + ar, "0123456789" * 2))

        if not re.fullmatch(r"\d{1,10}", code):
            raise forms.ValidationError("کد پرسنلی باید فقط شامل عدد (۱ تا ۱۰ رقم) باشد.")

        # مقدار نرمال‌شده را برگردون تا در cleaned_data جایگزین بشود
        return code

class RTLAuthForm(AuthenticationForm):
    """فرم لاگین با placeholder و راست‌به‌چپ؛ بدون تغییر لاجیک."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({
            "placeholder": "شماره پرسنلی",
            "autofocus": True,
            "dir": "ltr",
        })
        self.fields["password"].widget.attrs.update({
            "placeholder": "رمز عبور",
            "dir": "ltr",
        })

class EmployeeProfileForm(forms.ModelForm):
    class Meta:
        model = EmployeeProfile
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # لیست عنوان‌های موجود از دیتابیس (Distinct)
        titles = (EmployeeProfile.objects
                  .order_by()
                  .values_list("title", flat=True)
                  .distinct())
        # اگر دوست داری اسامی نقش‌ها هم به پیشنهادها اضافه شوند:
        role_names = (JobRole.objects
                      .order_by()
                      .values_list("name", flat=True)
                      .distinct())

        merged = sorted(set([t for t in titles if t] + [r for r in role_names if r]))

        # ویجت Title را به Datalist تبدیل کن (سرچیبلِ بدون تغییر مدل)
        if "title" in self.fields:
            self.fields["title"].widget = DatalistInput(options=merged, attrs={"class": "vTextField"})

class DatalistInput(forms.TextInput):
    """TextInput + <datalist> برای پیشنهادهای سرچ‌شونده (بدون تغییر مدل)."""
    def __init__(self, options=None, attrs=None):
        super().__init__(attrs)
        self.options = [o for o in (options or []) if (o or "").strip()]
        self.list_id = f"id_titles_{uuid4().hex[:8]}"

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        attrs["list"] = self.list_id
        input_html = super().render(name, value, attrs, renderer)
        opts = "".join(f'<option value="{escape(opt)}"></option>' for opt in self.options)
        return mark_safe(input_html + f'<datalist id="{self.list_id}">{opts}</datalist>')

class _NumericUsernameMixin:
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        f = self.fields['username']
        f.label = 'کد پرسنلی'
        f.help_text = 'فقط عدد (۱ تا ۱۰ رقم).'
        f.widget.attrs.update({'inputmode': 'numeric', 'pattern': r'\d{1,10}'})

    def clean_username(self):
        u = (self.cleaned_data.get('username') or '').strip()
        if not re.fullmatch(r'\d{1,10}', u):
            raise forms.ValidationError('نام کاربری باید فقط عدد (حداکثر ۱۰ رقم) باشد.')
        return u

class CustomUserCreationForm(_NumericUsernameMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username',)

class CustomUserChangeForm(_NumericUsernameMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = ('username',)
