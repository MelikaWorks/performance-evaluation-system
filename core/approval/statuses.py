# core/approval/statuses.py
from enum import Enum


class EvaluationStatus(str, Enum):
    # --- مرحله ایجاد ---
    DRAFT = "draft"                     # پیش‌نویس

    # --- ارسال کارمند ---
    SUBMITTED = "submitted"             # ارسال‌شده برای HR

    # --- HR ---
    HR_REVIEW = "hr_review"
    HR_APPROVED = "hr_approved"
    HR_REJECTED = "hr_rejected"

    # --- مدیر واحد ---
    MANAGER_REVIEW = "manager_review"
    MANAGER_APPROVED = "manager_approved"
    MANAGER_REJECTED = "manager_rejected"

    # --- مدیر کارخانه ---
    FACTORY_REVIEW = "factory_review"
    FACTORY_APPROVED = "factory_approved"
    FACTORY_REJECTED = "factory_rejected"

    # --- نهایی ---
    FINAL_APPROVED = "final_approved"
    FINAL_REJECTED = "final_rejected"
