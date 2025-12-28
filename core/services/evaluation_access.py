#core/services/evaluation_access.py
from __future__ import annotations
from django.http import HttpRequest
from django.contrib.auth.models import User

from core.models import (
    Evaluation,
    EmployeeProfile,
    Unit,
    Organization,
)

# اگر Enumها رو در models یا فایل جدا داری، اینجا ایمپورت کن:
# from.models import EvaluationStatus, RoleLevel

# ——— کمک‌کننده‌های نقش (این‌ها رو با منطق خودت پر می‌کنی) ———

def is_hr(user: User) -> bool:
    """چک کن این یوزر HR هست یا نه."""
    # TODO: اینجا منطق واقعی خودت رو بذار (مثلاً بر اساس role_level یا گروه‌ها)
    return getattr(user, "is_hr", False)

def is_unit_manager(user: User) -> bool:
    """مدیر واحد / سرپرست."""
    return getattr(user, "is_unit_manager", False)

def is_factory_manager(user: User) -> bool:
    """مدیر کارخانه."""
    return getattr(user, "is_factory_manager", False)

def is_employee(user: User) -> bool:
    """کارمند معمولی (نه HR، نه مدیر)."""
    # این فقط نمونه‌ست؛ تو با منطق واقعی پروژه‌ات عوضش کن
    return not (is_hr(user) or is_unit_manager(user) or is_factory_manager(user) or user.is_superuser)

def can_view_evaluation(user: User, ev: Evaluation) -> bool:
    """
    چه کسی مجاز است فرم را ببیند؟
    منطبق با مراحل گردش کار و نقش‌ها.
    """

    if user.is_superuser:
        return True

    # ✔ کارمند فقط فرم خودش را می‌بیند
    if ev.employee_id == user.id:
        return ev.status in {
            Evaluation.Status.DRAFT,
            Evaluation.Status.SUBMITTED,
            Evaluation.Status.FINAL_APPROVED,
        }

    # ✔ ارزیاب (manager اولیه)
    if ev.evaluator_id == user.id:
        return True

    # ✔ HR → فقط مرحله HR و مرحله نهایی
    if is_hr(user):
        return ev.status in {
            Evaluation.Status.HR_REVIEW,
            Evaluation.Status.FINAL_APPROVED,
        }

    # ✔ مدیر واحد → فقط مرحله خودش و مرحله نهایی
    if is_unit_manager(user):
        return ev.status in {
            Evaluation.Status.MANAGER_REVIEW,
            Evaluation.Status.FINAL_APPROVED,
        }

    # ✔ مدیر کارخانه → فقط مرحله خودش و مرحله نهایی
    if is_factory_manager(user):
        return ev.status in {
            Evaluation.Status.FACTORY_REVIEW,
            Evaluation.Status.FINAL_APPROVED,
        }

    return False

def can_edit_evaluation(user: User, ev: Evaluation) -> bool:
    """
    آیا این یوزر اجازه ویرایش متن فرم را دارد؟
    فقط در DRAFT و فقط ارزیاب (evaluator)
    """

    if user.is_superuser:
        return True

    # فقط وقتی فرم DRAFT است → قابل ویرایش
    if ev.status != Evaluation.Status.DRAFT:
        return False

    # فقط ارزیاب فرم اجازه ویرایش دارد
    return ev.evaluator_id == user.id

def can_approve_evaluation(user: User, ev: Evaluation) -> bool:
    """
    آیا این یوزر اجازه Approve/Reject این فرم را دارد؟
    منطبق با گردش‌کار جدید.
    """

    if user.is_superuser:
        return True

    # ❌ Final Approved → هیچ‌کس اجازه تغییر ندارد
    if ev.status == Evaluation.Status.FINAL_APPROVED:
        return False

    # ✔ HR → فقط در مرحله HR_REVIEW
    if is_hr(user) and ev.status == Evaluation.Status.HR_REVIEW:
        return True

    # ✔ مدیر واحد → فقط در مرحله MANAGER_REVIEW
    if is_unit_manager(user) and ev.status == Evaluation.Status.MANAGER_REVIEW:
        return True

    # ✔ مدیر کارخانه → فقط در مرحله FACTORY_REVIEW
    if is_factory_manager(user) and ev.status == Evaluation.Status.FACTORY_REVIEW:
        return True

    # ✔ ارزیاب → فقط در SUBMITTED (مرحله قدیمی که اول چرخه است)
    if ev.status == Evaluation.Status.SUBMITTED and ev.evaluator_id == user.id:
        return True

    return False


