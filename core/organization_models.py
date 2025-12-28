# core/organization_models.py
from django.db import models

class Holding(models.Model):
    name = models.CharField(max_length=100, unique=True)
    headquarters_city = models.CharField(max_length=100, default="Tehran")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

class DepartmentGroup(models.Model):
    """
    گروه واحدهای مشترک (مثلاً HR یا IT) که می‌تونن بین چند کارخانه shared باشن.
    """
    name = models.CharField(max_length=100)  # HR Qazvin, IT ShamsAbad, ...
    factories = models.ManyToManyField(
        "Organization",
        related_name="department_groups",
        blank=True
    )

    class Meta:
        ordering = ["name"]
        unique_together = [("name",)]

    def __str__(self):
        return self.name

class BaseScopedModel(models.Model):
    """
    میکسین انتزاعی: برای مدل‌هایی که باید به حوزه‌ها متصل باشن.
    بعداً در EvaluationForm، Unit، EmployeeProfile ازش استفاده می‌کنیم.
    """
    holding = models.ForeignKey(Holding, on_delete=models.PROTECT, null=True, blank=True)
    factory = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="factory_units"
    )

    class Meta:
        abstract = True


