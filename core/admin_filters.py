from django.contrib.admin import SimpleListFilter
from core.models import Organization

class OrganizationQuickFilter(SimpleListFilter):
    title = "سازمان"
    parameter_name = "org"

    def lookups(self, request, model_admin):
        orgs = Organization.objects.all().values_list("id", "name")
        return [("all", "همه")] + list(orgs)

    def queryset(self, request, queryset):
        value = self.value()
        if not value or value == "all":
            return queryset
        return queryset.filter(organization_id=value)
