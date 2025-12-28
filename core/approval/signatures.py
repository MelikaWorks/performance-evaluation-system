# core/approval/signatures.py
"""
Signature approval domain logic.

NOTE:
- Django model: evaluations.models.EvaluationSignature
- This module contains approval rules and validation only.
- No database models should be defined here.
"""
from .roles import ApprovalRole

# ترتیب مراحل تأیید
APPROVAL_CHAIN = [
    ApprovalRole.MANAGER,
    ApprovalRole.HR,
    ApprovalRole.FACTORY_MANAGER,
    ApprovalRole.FINAL,
]
