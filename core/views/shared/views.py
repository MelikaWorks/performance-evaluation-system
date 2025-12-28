from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from core.services.access import visible_employee_profiles


@login_required
def people_list(request):
    qs = visible_employee_profiles(request.user).select_related("user","unit","job_role")
    return render(request, "people_list.html", {"profiles": qs})

