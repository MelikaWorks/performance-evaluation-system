# ======================================================
# core/constants.py
# Centralized system-wide constants for Evaluation System
# Author: Melika Mehranpour
# Last updated: November 2025
# ======================================================
class Settings:
    UNIT_CODE_CHOICES = [
        ("100", "مدیریت — 100"),
        ("207", "امور مالی — 207"),
        ("216", "حراست و انتظامات — 216"),
        ("219", "لجستیک — 219"),
        ("230", "تدارکات — 230"),
        ("202", "منابع انسانی — 202"),
    ]
    # ---- نقش‌ها ----
    ROLE_FACTORY_MANAGER = "900"  # مدیر کارخانه
    ROLE_UNIT_MANAGER = "901"  # مدیر واحد
    ROLE_SECTION_HEAD = "902"  # رئیس واحد
    ROLE_SUPERVISOR = "903"  # سرپرست
    ROLE_EMPLOYEE = "904"  # کارمند / اپراتور
    ROLE_RESPONSIBLE = "907"  # مسئول
    ROLE_EXPERT = "906"  # کارشناس
    ROLE_TECHNICIAN = "908"  # کاردان
    ROLE_OFFICE_ASSISTANT = "909"  # مسئول دفتر مدیر کارخانه
    #ROLE_SUPPLY_EMPLOYEE = "905"  # کارمند تدارکات

    HEAD_UNIT_CODES = {"100"}
    LOGISTICS_UNIT_CODES = {"219"}
    FINANCE_UNIT_CODES = {"207"}
    SECURITY_UNIT_CODES = {"216"}
    HR_UNIT_CODES = {"202"}  # منابع انسانی

    ORG_HEAD_PCODE = "220001"
    DEFAULT_PARENT_NAME = "مدیریت"

    EXCEPTION_MANAGER_ROLE_BY_UNIT_CODE = {"230": "مدیر برنامه ريزي و سيستم ها"}
    EXTERNAL_MANAGER_SOURCE = {"230": "114"}

    ALLOW_900_MANAGER_CODES = (
            HEAD_UNIT_CODES | LOGISTICS_UNIT_CODES | FINANCE_UNIT_CODES | SECURITY_UNIT_CODES
    )
    ALLOW_900_MANAGER_NAMES = {
        "مدیریت", "لجستیک", "تحقیق و توسعه",
        "حراست", "حراست و انتظامات", "امور مالی", "حسابداری",
    }

    COMPANY_NAME = "<a href='http://haftalmas.com/'>Haft Almas Ind.co</a>"
    COPYRIGHT_FOOTER = (
        "© 2025 Development & Design by "
        "<b><a href='mailto:melika.works@gmail.com'>Melika Mehranpour</a></b> — All rights reserved."
    )

    DEFAULT_LANGUAGE = "fa"
    DATE_FORMAT = "%Y-%m-%d"
    # ======================================================
    # Evaluation & HR Form Configuration
    # ======================================================
    # ---- پیکربندی فرم‌های ارزیابی (Target Roles) ----
    # هر فرم HR-F مشخص می‌کند که چه نقش‌هایی (JobRole.code)
    # به‌عنوان ارزیابی‌شونده (target) در آن فرم قرار دارند.
    # ---- فرم‌های ارزیابی ----
    FORM_CODE_EMPLOYEE = "HR-F-80"
    FORM_CODE_TECHNICIAN = "HR-F-81"
    FORM_CODE_SUPERVISOR = "HR-F-82"
    FORM_CODE_EXPERT = "HR-F-83"
    FORM_CODE_MANAGER = "HR-F-84"

    FORM_TARGET_ROLES = {
        # "HR-F-80": [904],  # کارمند / اپراتور
        # "HR-F-81": [908],  # کاردان
        # "HR-F-82": [903, 907],  # سرپرست + مسئول
        # "HR-F-83": [906],  # کارشناس
        # "HR-F-84": [901, 902],  # مدیر + رئیس
        "HR-F-80": [ROLE_EMPLOYEE],  # کارمند / اپراتور
        "HR-F-81": [ROLE_TECHNICIAN],  # کاردان
        "HR-F-82": [ROLE_SUPERVISOR, ROLE_RESPONSIBLE, ROLE_OFFICE_ASSISTANT],  # سرپرست + مسئول
        "HR-F-83": [ROLE_EXPERT],  # کارشناس
        "HR-F-84": [ROLE_UNIT_MANAGER, ROLE_SECTION_HEAD],  # مدیر + رئیس
    }

    # ---- محدوده‌های ویژه‌ی مدیر کارخانه ----
    # این مقادیر برای فرم‌ها و دسترسی‌های خاص مدیر کارخانه (Factory Manager)
    # استفاده می‌شوند تا مشخص شود چه واحدهایی مستقیماً زیر نظر او هستند.
    FACTORY_LOGISTICS_UNITS = ["219"]  # لجستیک
    FACTORY_RND_UNITS = ["208"]  # تحقیق‌وتوسعه

    # کد نقش مسئول دفتر مدیر کارخانه (فقط یک نفر)
    FACTORY_OFFICE_ROLE_CODE = "909"

    # مجموع واحدهای ویژه‌ی مدیر کارخانه
    FACTORY_SPECIALIST_UNITS = FACTORY_LOGISTICS_UNITS + FACTORY_RND_UNITS


class WorkflowStatus:
    HR_REVIEW = "hr_review"
    MANAGER_REVIEW = "manager_review"
    FACTORY_REVIEW = "factory_review"

    HR_REJECTED = "hr_rejected"
    MANAGER_REJECTED = "manager_rejected"
    FACTORY_REJECTED = "factory_rejected"

    FINAL_APPROVED = "final_approved"


