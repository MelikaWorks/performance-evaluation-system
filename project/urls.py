# project/urls.py
from django.contrib import admin
from django.urls import path, include, reverse_lazy
from django.views.generic import TemplateView, RedirectView
from django.contrib.auth import views as auth_views
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
# مسیر خروج ادمین مستقل از logout عمومی
from django.contrib.auth.views import LogoutView

urlpatterns = [
    # مسیر تغییر رمز اختصاصی برای ادمین Django
    path("admin/password_change/", PasswordChangeView.as_view(template_name="admin/password_change_form.html",success_url="/admin/password_change/done/"),name="admin_password_change", ),
    path("admin/password_change/done/", PasswordChangeDoneView.as_view(template_name="admin/password_change_done.html"),name="admin_password_change_done", ),

    # 🟣 1️⃣ مسیرهای ادمین Django (باید همیشه بالاتر باشند)
    path("admin/logout/", LogoutView.as_view(next_page="/admin/login/"), name="admin_logout_override"),
    path("admin/reports/", include("core.urls.admin_reports_urls")),
    path("admin/", admin.site.urls),
    # 🟢 2️⃣ مسیرهای مدیر سیستم ارزیابی
    path("manager/login/",ensure_csrf_cookie(auth_views.LoginView.as_view(template_name="manager/login.html",redirect_authenticated_user=True)),name="manager_login",),
    path("manager/logout/",auth_views.LogoutView.as_view(next_page=reverse_lazy("manager_login")),name="manager_logout",),
    path("manager/password_change/",auth_views.PasswordChangeView.as_view(template_name="manager/password_change_form.html",success_url=reverse_lazy("manager_password_change_done"),), name="manager_password_change",),
    path("manager/password_change/done/",TemplateView.as_view(template_name="manager/password_change_done.html"),name="manager_password_change_done",),
    path("manager/", include(("core.urls.manager_urls", "manager"), namespace="manager")),

    # 🟡 3️⃣ مسیرهای احراز هویت عمومی
    path("accounts/login/", ensure_csrf_cookie(auth_views.LoginView.as_view(template_name="registration/login.html", redirect_authenticated_user=True)),name="login",),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page=reverse_lazy("login")),name="logout",),
    path("accounts/password_change/",auth_views.PasswordChangeView.as_view(template_name="registration/password_change_form.html",success_url=reverse_lazy("password_change_done"),),name="password_change",),
    path("accounts/password_change/done/",auth_views.PasswordChangeDoneView.as_view(template_name="registration/password_change_done.html"),name="password_change_done",),
    path("accounts/", include("django.contrib.auth.urls")),
    path("eval/login/", RedirectView.as_view(url="/accounts/login/", permanent=False)),

    # ⚪ 4️⃣ مسیرهای جانبی و اصلی
    path("select2/", include("django_select2.urls")),
    path("", include("core.urls")),

    path("approval/", include("core.urls.approval_urls")),
]


