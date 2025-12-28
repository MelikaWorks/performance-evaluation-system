# core/approval/workflow.py
from .roles import ApprovalRole
from .statuses import EvaluationStatus

class ApprovalWorkflow:
    """
    موتور تصمیم‌گیر برای گردش کار ارزیابی.
    فقط با status و role کار می‌کند.
    """

    def __init__(self, status):
        self.status = EvaluationStatus(status)

    # --------------------------------------------------------
    # تعیین مرحله فعلی
    # --------------------------------------------------------
    def current_step(self):
        mapping = {
            EvaluationStatus.SUBMITTED: ApprovalRole.HR,
            EvaluationStatus.FACTORY_REVIEW: ApprovalRole.FACTORY_MANAGER,
            EvaluationStatus.FINAL_APPROVED: ApprovalRole.FINAL,
        }
        return mapping.get(self.status, None)

    # --------------------------------------------------------
    # آیا این نقش می‌تواند approve کند؟
    # --------------------------------------------------------
    def can_approve(self, role: ApprovalRole):
        return self.current_step() == role

    # --------------------------------------------------------
    # آیا می‌تواند فرم را برگرداند؟
    # --------------------------------------------------------
    def can_return(self, role: ApprovalRole):
        # HR همیشه حق ریجکت دارد
        if role == ApprovalRole.HR:
            return True

        # سایر نقش‌ها فقط اگر اجازه approve دارند
        return self.can_approve(role)

    # --------------------------------------------------------
    # وضعیت جدید بعد از approve
    # --------------------------------------------------------
    def approve_status(self):
        if self.status == EvaluationStatus.SUBMITTED:
            return EvaluationStatus.FACTORY_REVIEW

        if self.status == EvaluationStatus.FACTORY_REVIEW:
            return EvaluationStatus.FINAL_APPROVED

        return None

    # --------------------------------------------------------
    # وضعیت جدید بعد از return
    # --------------------------------------------------------
    def return_status(self):
        return EvaluationStatus.DRAFT

