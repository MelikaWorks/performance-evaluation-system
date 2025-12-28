# core/approval/roles.py

from enum import Enum

class ApprovalRole(str, Enum):
    HR = "hr"
    MANAGER = "manager"
    FACTORY_MANAGER = "factory_manager"
    FINAL = "final"
