# core/services/permissions.py
# -*- coding: utf-8 -*-
"""
منطق دسترسی ارزیابی (چه کسی، چه کسی را با کدام فرم ارزیابی کند)
قواعد فعلی (طبق صحبت‌های اخیر):
- HR-F-80: برای کارکنان/اپراتورها (role 904). ارزیاب: مدیر/رئیس (901/902) و همچنین سرپرست یا کارشناس مسئول (903/907).
- HR-F-81: برای کاردان‌ها (role 908) [در صورت باقی ماندن 905، آن هم پذیرفته می‌شود]. ارزیاب: فقط مدیر/رئیس (901/902).
- HR-F-82: برای کارشناس مسئول (role 903 و 907). ارزیاب: فقط مدیر/رئیس (901/902).
- HR-F-83: برای کارشناس‌ها (role 906). ارزیاب: فقط مدیر/رئیس (901/902).
- HR-F-84: برای مدیر/رئیس واحد (roles 901/902). ارزیاب: فقط مدیر کارخانه (role 900).
- مدیر کارخانه (900) فعلاً خودش ارزیابی نمی‌شود.
نکته‌ی توسعه: می‌توان محدودیت «هم‌واحد بودن» (unit_code) را نیز enforce کرد.
"""

from enum import IntEnum
from typing import Set, Dict, List
from typing import Optional
from core.constants import Settings

# --- تعریف role_level ها به‌صورت Enum برای خوانایی بهتر ---
class RoleLevel(IntEnum):
    FACTORY_MANAGER = int(Settings.ROLE_FACTORY_MANAGER)   # مدیر کارخانه
    MANAGER         = int(Settings.ROLE_UNIT_MANAGER)  # مدیر
    CHIEF           = int(Settings.ROLE_SECTION_HEAD)  # رئیس
    SUPERVISOR      = int(Settings.ROLE_SUPERVISOR)  # سرپرست903
    EMPLOYEE        = int(Settings.ROLE_EMPLOYEE)  # سایر پرسنل/کارمند/اپراتور904
    TECHNICIAN      = 905  # (قدیمی) کاردان - اگر باقی مانده905
    ASSOCIATE       = int(Settings.ROLE_TECHNICIAN)  # کاردان (تعریف جدید)908
    SPECIALIST      = int(Settings.ROLE_EXPERT)  # کارشناس906
    SENIOR_SPEC     = int(Settings.ROLE_RESPONSIBLE)  # کارشناس مسئول907
    OFFICE_ASSISTANT = int(Settings.ROLE_OFFICE_ASSISTANT) # مسئول دفتر مدیر کارخانه909

# --- نقش‌های هدف هر فرم (کسی که ارزیابی می‌شود) ---
FORM_EMPLOYEE_ROLES: Dict[str, Set[int]] = {
    Settings.FORM_CODE_EMPLOYEE: {RoleLevel.EMPLOYEE},                         # 904
    Settings.FORM_CODE_TECHNICIAN: {RoleLevel.ASSOCIATE, RoleLevel.TECHNICIAN},  # 908 (+905 در صورت وجود)
    Settings.FORM_CODE_SUPERVISOR: {RoleLevel.SUPERVISOR, RoleLevel.SENIOR_SPEC},# 903, 907
    Settings.FORM_CODE_EXPERT: {RoleLevel.SPECIALIST},                       # 906
    Settings.FORM_CODE_MANAGER: {RoleLevel.MANAGER, RoleLevel.CHIEF},         # 901, 902
}

# --- نقش‌های مجازِ ارزیاب برای هر فرم ---
EVALUATOR_ROLES_BY_FORM: Dict[str, Set[int]] = {
    Settings.FORM_CODE_EMPLOYEE: {RoleLevel.MANAGER, RoleLevel.CHIEF, RoleLevel.SUPERVISOR, RoleLevel.SENIOR_SPEC},
    Settings.FORM_CODE_TECHNICIAN: {RoleLevel.MANAGER, RoleLevel.CHIEF},
    Settings.FORM_CODE_SUPERVISOR: {RoleLevel.MANAGER, RoleLevel.CHIEF},
    Settings.FORM_CODE_EXPERT: {RoleLevel.MANAGER, RoleLevel.CHIEF},
    Settings.FORM_CODE_MANAGER: {RoleLevel.FACTORY_MANAGER, RoleLevel.MANAGER},
}

# --- فرم پیش‌فرض هر نقش (برای انتخاب خودکار فرم) ---
DEFAULT_FORM_BY_ROLE: Dict[int, str] = {
    RoleLevel.EMPLOYEE:     Settings.FORM_CODE_EMPLOYEE,
    RoleLevel.ASSOCIATE:    Settings.FORM_CODE_TECHNICIAN,
    RoleLevel.TECHNICIAN:   Settings.FORM_CODE_TECHNICIAN,   # اگر 905 باقی باشد
    RoleLevel.SUPERVISOR:   Settings.FORM_CODE_SUPERVISOR,
    RoleLevel.SENIOR_SPEC:  Settings.FORM_CODE_SUPERVISOR,
    RoleLevel.SPECIALIST:   Settings.FORM_CODE_EXPERT,
    RoleLevel.MANAGER:      Settings.FORM_CODE_MANAGER,
    RoleLevel.CHIEF:        Settings.FORM_CODE_MANAGER,
    # RoleLevel.FACTORY_MANAGER:  None  # فعلاً ارزیابی نمی‌شود
}

def eligible_forms_for_employee(employee_role: int) -> List[str]:
    """فرم‌های مجاز برای نقشِ کارمندِ ارزیابی‌شونده."""
    return [code for code, roles in FORM_EMPLOYEE_ROLES.items() if employee_role in roles]

def default_form_for_employee(employee_role: int) -> Optional[str]:
    """فرم پیش‌فرض برای نقشِ کارمند (در صورت وجود)."""
    return DEFAULT_FORM_BY_ROLE.get(employee_role)

def can_evaluate(
    evaluator_role: int,
    employee_role: int,
    form_code: str,
    *,
    evaluator_unit: Optional[str] = None,
    employee_unit: Optional[str] = None,
    require_same_unit: bool = True,
) -> bool:

    """
    آیا این ارزیاب اجازه دارد این کارمند را با این فرم ارزیابی کند؟
    - قواعد عمومی از EVALUATOR_ROLES_BY_FORM و FORM_EMPLOYEE_ROLES خوانده می‌شود.
    - اگر require_same_unit=True باشد، «هم‌واحد بودن» الزام می‌شود؛
      اما مدیر کارخانه (900) حق عبور دارد (برای HR-F-84).
    """
    # فرم مدیران (HR-F-84)
    if form_code == Settings.FORM_CODE_MANAGER:
        # مدیر کارخانه: می‌تواند مدیر/رئیس را ارزیابی کند (بدون شرط واحد)
        if evaluator_role == RoleLevel.FACTORY_MANAGER:  # 900
            return employee_role in (RoleLevel.MANAGER, RoleLevel.CHIEF)

        # مدیر واحد: فقط رؤسای همان واحد را
        if evaluator_role == RoleLevel.MANAGER:  # 901
            if employee_role == RoleLevel.CHIEF:
                return (not require_same_unit) or (evaluator_unit and employee_unit and evaluator_unit == employee_unit)
            return False

        # سایرین حق ندارند
        return False

    # قواعد عمومی برای سایر فرم‌ها
    code = (form_code or "").strip().upper()
    if code not in FORM_EMPLOYEE_ROLES:
        return False

    # آیا نقش کارمند با فرم هم‌خوان است؟
    if employee_role not in FORM_EMPLOYEE_ROLES[code]:
        return False

    # آیا نقش ارزیاب برای این فرم مجاز است؟
    allowed_evaluators = EVALUATOR_ROLES_BY_FORM.get(code, set())
    if evaluator_role not in allowed_evaluators:
        return False

    # الزام «هم‌واحد بودن» (در صورت فعال بودن)، بجز مدیر کارخانه
    if require_same_unit and evaluator_role != RoleLevel.FACTORY_MANAGER:
        if evaluator_unit and employee_unit and (str(evaluator_unit) != str(employee_unit)):
            return False

    return True

__all__ = [
    "RoleLevel",
    "FORM_EMPLOYEE_ROLES",
    "EVALUATOR_ROLES_BY_FORM",
    "DEFAULT_FORM_BY_ROLE",
    "eligible_forms_for_employee",
    "default_form_for_employee",
    "can_evaluate",
]
