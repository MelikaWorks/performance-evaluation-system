## Signature Model (Draft)

هر امضا شامل اطلاعات زیر است:

- evaluator (User)
- role (Manager / HR / Factory)
- signed_at (datetime)
- comment (optional)
- is_final (bool)

ارتباط‌ها:
- هر Evaluation می‌تواند چند امضا داشته باشد
- ترتیب امضاها:
  1. Manager
  2. HR
  3. Factory Manager

قوانین:
- امضاها قابل ویرایش یا حذف نیستند
- فقط یک امضا برای هر role مجاز است
- بعد از امضای Factory، ارزیابی قفل می‌شود

## Evaluation Status Flow (Draft)

Statusها و معنی آن‌ها:

- DRAFT
  ارزیابی در حال تکمیل توسط مدیر واحد

- SUBMITTED
  ارسال شده توسط مدیر واحد، در انتظار HR

- HR_APPROVED
  بررسی و تأیید شده توسط HR، در انتظار مدیر کارخانه

- FACTORY_APPROVED
  تأیید شده توسط مدیر کارخانه
  آماده تأیید نهایی

- FINAL_APPROVED
  ارزیابی نهایی شده
  فقط خواندنی

- REJECTED
  برگشت داده شده به مرحله قبل

## Signature → Status Mapping

- Manager Signature
  From: DRAFT
  To: SUBMITTED

- HR Signature
  From: SUBMITTED
  To: HR_APPROVED

- Factory Manager Signature
  From: HR_APPROVED
  To: FACTORY_APPROVED

- Final Approval
  From: FACTORY_APPROVED
  To: FINAL_APPROVED

قوانین:
- ثبت هر امضا فقط در status مربوط به خودش مجاز است
- اگر status هم‌خوان نباشد، امضا ثبت نمی‌شود
- REJECTED می‌تواند از هر مرحله به مرحله قبل برگردد


