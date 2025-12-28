# core/admin_org.py
from django.contrib import admin
from .organization_models import Holding, DepartmentGroup
from django.contrib.admin import SimpleListFilter

class FactoryFilter(SimpleListFilter):
  title = "کارخانه"
  parameter_name = "factory"

  def lookups(self, request, model_admin):
    factories = model_admin.model.objects.all().values_list("id", "name")
    # گزینه‌ی "همه" را در اول فهرست قرار می‌دهیم
    return [("all", "همه")] + list(factories)

  def queryset(self, request, queryset):
    value = self.value()
    if not value or value == "all":
      return queryset  # بدون فیلتر
    return queryset.filter(id=value)


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
  list_display = ("name", "headquarters_city")
  search_fields = ("name", "headquarters_city")

# @admin.register(Factory)
# class FactoryAdmin(admin.ModelAdmin):
#   list_display = ("name", "city", "city_code", "is_head_factory", "holding")
#   list_filter = ("holding", "city_code", "is_head_factory")
#   search_fields = ("name", "city", "city_code")

@admin.register(DepartmentGroup)
class DepartmentGroupAdmin(admin.ModelAdmin):
  list_display = ("name",)
  search_fields = ("name",)
  filter_horizontal = ("factories",)



