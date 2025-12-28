# core/urls/__init__.py
from django.urls import path, include

urlpatterns = [
    path("manager/", include("core.urls.manager_urls")),
    path("reports/", include("core.urls.admin_reports_urls")),
]
