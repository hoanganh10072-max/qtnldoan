from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import *

admin.site.site_header = "FPT HRM - Quản trị hệ thống"
admin.site.register(User, UserAdmin)
for model in [Department, Position, Employee, Contract, JobOpening, Candidate, Attendance, LeaveType, LeaveRequest, PayrollPeriod, Payroll, Transfer]:
    admin.site.register(model)
