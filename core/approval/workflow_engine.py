# core/approval/workflow_engine.py
from django.utils import timezone
from core.models import  EmployeeProfile
from core.models import EvaluationSignature
from core.approval.statuses import EvaluationStatus
from core.constants import Settings
from core.approval.roles import ApprovalRole
from core.approval.workflow import ApprovalWorkflow

LEGACY_STATUS_MAP = {
    "draft": EvaluationStatus.DRAFT,
    "submitted": EvaluationStatus.SUBMITTED,
    "approved": EvaluationStatus.FINAL_APPROVED,
    #"rejected": EvaluationStatus.REJECTED,
}

class WorkflowEngine:
    """
    این کلاس، کُنش‌گر اصلی گردش‌کار است:
    1) وضعیت فعلی را از workflow.py می‌گیرد
    2) نقش کاربر را تعیین می‌کند
    3) روی Evaluation واقعی تغییرات را اعمال می‌کند
    """

    def __init__(self, evaluation):
        if evaluation is None:
            raise ValueError("Evaluation cannot be None")

        self.evaluation = evaluation

        raw_status = evaluation.status

        # 🔑 فیکس حیاتی: تبدیل enum جنگویی
        if hasattr(raw_status, "value"):
            raw_status = raw_status.value

        try:
            status = EvaluationStatus(raw_status)
        except ValueError:
            status = LEGACY_STATUS_MAP.get(raw_status)

        if not status:
            raise ValueError(f"Unsupported evaluation status: {raw_status}")

        self.core = ApprovalWorkflow(status)

    # ---------------------------------------
    # نقش کاربر برای این Evaluation چیست؟
    # ---------------------------------------
    def get_user_role(self, user):
        ep = EmployeeProfile.objects.filter(user=user).first()
        if not ep or not ep.job_role:
            return None

        # ✅ HR واقعی طبق constants
        if (
                ep.unit
                and ep.unit.unit_code in Settings.HR_UNIT_CODES  # {"202"}
                and ep.job_role.code == Settings.ROLE_UNIT_MANAGER  # "901"
        ):
            return ApprovalRole.HR

        # مدیر کارخانه
        if ep.job_role.code == Settings.ROLE_FACTORY_MANAGER:  # "900"
            return ApprovalRole.FACTORY_MANAGER

        # مدیر / سرپرست / مسئول
        if ep.job_role.code in {
            Settings.ROLE_UNIT_MANAGER,  # 901
            Settings.ROLE_SUPERVISOR,  # 903
            Settings.ROLE_RESPONSIBLE,  # 907
            Settings.ROLE_SECTION_HEAD,  # 902
        }:
            return ApprovalRole.MANAGER

        return None

    # ---------------------------------------
    # آیا این کاربر اجازه Approve دارد؟
    # ---------------------------------------
    def can_approve(self, user):
        role = self.get_user_role(user)
        return self.core.can_approve(role)

    # ---------------------------------------
    # ثبت تأیید
    # ---------------------------------------
    def approve(self, user):
        role = self.get_user_role(user)
        if not role:
            raise PermissionError("نقش کاربر مشخص نیست.")

        # آیا در این مرحله اجازه تأیید دارد؟
        if not self.core.can_approve(role):
            raise PermissionError("شما مجاز به تأیید این مرحله نیستید.")

        # وضعیت بعدی workflow
        new_status = self.core.approve_status()
        if not new_status:
            raise ValueError("مرحله بعدی وجود ندارد.")

        # ثبت امضا (فقط یک بار برای هر role)
        ep = EmployeeProfile.objects.filter(user=user).first()

        EvaluationSignature.objects.get_or_create(
            evaluation=self.evaluation,
            role=role.value,
            defaults={
                "evaluator": user,
                "signed_by_name": (
                    ep.user.get_full_name()
                    if ep and ep.user.get_full_name()
                    else user.get_full_name() or user.username
                ),
                "is_final": (role == ApprovalRole.FACTORY_MANAGER),
            }
        )

        # به‌روزرسانی وضعیت ارزیابی
        self.evaluation.status = new_status
        self.evaluation.updated_at = timezone.now()
        self.evaluation.save(update_fields=["status", "updated_at"])

        return new_status

    # ---------------------------------------
    # ثبت برگشت به مرحله قبل
    # ---------------------------------------
    def return_for_edit(self, user):
        role = self.get_user_role(user)
        if not self.core.can_return(role):
            raise PermissionError("اجازه برگشت این مرحله را ندارید.")

        new_status = self.core.return_status()
        if not new_status:
            raise ValueError("مرحله برگشت برای این مرحله تعریف نشده.")

        self.evaluation.status = new_status
        self.evaluation.updated_at = timezone.now()
        self.evaluation.save()

        return new_status

    def has_signature(self, role):
        """
        Check if the given role has already signed this evaluation.
        This is a read-only check.
        """
        if not hasattr(self.evaluation, "signatures"):
            return False

        return self.evaluation.signatures.filter(role=role).exists()

    def can_sign(self, role):
        """
        Check whether the given role is allowed to sign
        at the current stage of the workflow.
        """
        # نقش بعدی در زنجیره
        expected_role = self.core.current_step()

        if role != expected_role:
            return False

        # اگر قبلاً امضا کرده، دوباره نمی‌تواند
        if self.has_signature(role):
            return False

        return True

    def can_user_approve(self, user):
        ep = getattr(user, "employee_profile", None)
        if not ep or not ep.job_role:
            return False

        # HR Manager
        if (
                ep.unit
                and ep.unit.unit_code in Settings.HR_UNIT_CODES
                and ep.job_role.code == Settings.ROLE_UNIT_MANAGER
        ):
            return self.core.can_approve(ApprovalRole.HR)

        # Factory Manager
        if ep.job_role.code == Settings.ROLE_FACTORY_MANAGER:
            return self.core.can_approve(ApprovalRole.FACTORY_MANAGER)

        return False