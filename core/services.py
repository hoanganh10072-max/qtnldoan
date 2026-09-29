import calendar
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Attendance, Candidate, Employee, LeaveRequest, Payroll, PayrollPeriod, Transfer, User


@transaction.atomic
def convert_candidate(candidate, cleaned_data):
    locked = Candidate.objects.select_for_update().select_related("job_opening__department").get(pk=candidate.pk)
    if locked.converted_employee_id or locked.status == Candidate.Status.HIRED:
        raise ValidationError("Ứng viên đã được tiếp nhận.")
    if locked.status != Candidate.Status.PASSED:
        raise ValidationError("Chỉ ứng viên đạt yêu cầu mới được tiếp nhận.")
    user = User.objects.create_user(
        username=cleaned_data["username"], password=cleaned_data["password"],
        email=locked.email, role=User.Role.EMPLOYEE,
    )
    employee = Employee.objects.create(
        full_name=locked.full_name, date_of_birth=cleaned_data["date_of_birth"],
        gender=cleaned_data["gender"], citizen_id=cleaned_data["citizen_id"],
        email=locked.email, phone=locked.phone, address=cleaned_data["address"],
        hire_date=cleaned_data["hire_date"], department=locked.job_opening.department,
        position=cleaned_data["position"], base_salary=cleaned_data["base_salary"], user=user,
    )
    locked.status = Candidate.Status.HIRED
    locked.converted_employee = employee
    locked.save(update_fields=["status", "converted_employee", "updated_at"])
    return employee


@transaction.atomic
def check_in(employee, moment=None):
    moment = timezone.localtime(moment or timezone.now())
    attendance, created = Attendance.objects.get_or_create(
        employee=employee, work_date=moment.date(), defaults={"check_in": moment.time().replace(microsecond=0)}
    )
    if not created:
        raise ValidationError("Bạn đã chấm công vào hôm nay.")
    return attendance


@transaction.atomic
def check_out(employee, moment=None):
    moment = timezone.localtime(moment or timezone.now())
    try:
        attendance = Attendance.objects.select_for_update().get(employee=employee, work_date=moment.date())
    except Attendance.DoesNotExist as exc:
        raise ValidationError("Bạn chưa chấm công vào hôm nay.") from exc
    if attendance.check_out:
        raise ValidationError("Bạn đã chấm công ra hôm nay.")
    attendance.check_out = moment.time().replace(microsecond=0)
    attendance.save()
    return attendance


@transaction.atomic
def decide_leave(leave_request, approver, approve, rejection_reason=""):
    item = LeaveRequest.objects.select_for_update().get(pk=leave_request.pk)
    if item.status != LeaveRequest.Status.PENDING:
        raise ValidationError("Đơn đã được xử lý, không thể duyệt lại.")
    if not approve and not rejection_reason.strip():
        raise ValidationError("Bắt buộc nhập lý do từ chối.")
    item.status = LeaveRequest.Status.APPROVED if approve else LeaveRequest.Status.REJECTED
    item.approver = approver
    item.rejection_reason = "" if approve else rejection_reason.strip()
    item.save()
    return item


def actual_work_days(employee, period):
    attendances = Attendance.objects.filter(employee=employee, work_date__year=period.year, work_date__month=period.month)
    total = Decimal("0")
    for item in attendances:
        if item.hours_worked >= 4:
            total += Decimal("1")
        elif item.hours_worked > 0:
            total += Decimal("0.5")
    paid_leave = LeaveRequest.objects.filter(
        employee=employee, status=LeaveRequest.Status.APPROVED, leave_type__is_paid=True,
        start_date__year=period.year, start_date__month=period.month,
    ).aggregate(total=Sum("days"))["total"] or 0
    return min(total + Decimal(paid_leave), period.standard_days)


@transaction.atomic
def generate_payrolls(period):
    locked = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
    if locked.status != PayrollPeriod.Status.DRAFT:
        raise ValidationError("Kỳ lương đã khóa.")
    for employee in Employee.objects.filter(status=Employee.Status.ACTIVE):
        Payroll.objects.get_or_create(
            period=locked, employee=employee,
            defaults={
                "base_salary": employee.base_salary,
                "standard_days": locked.standard_days,
                "actual_days": actual_work_days(employee, locked),
            },
        )
    return locked.payrolls.count()


@transaction.atomic
def approve_payroll_period(period, approver):
    locked = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
    if locked.status != PayrollPeriod.Status.DRAFT:
        raise ValidationError("Kỳ lương đã được xử lý.")
    if not locked.payrolls.exists():
        raise ValidationError("Kỳ lương chưa có bảng lương.")
    locked.status = PayrollPeriod.Status.APPROVED
    locked.approved_by = approver
    locked.save(update_fields=["status", "approved_by", "updated_at"])
    return locked


@transaction.atomic
def create_transfer(cleaned_data):
    employee = Employee.objects.select_for_update().get(pk=cleaned_data["employee"].pk)
    return Transfer.objects.create(
        employee=employee, old_department=employee.department, old_position=employee.position,
        new_department=cleaned_data["new_department"], new_position=cleaned_data["new_position"],
        effective_date=cleaned_data["effective_date"], reason=cleaned_data["reason"],
    )


@transaction.atomic
def decide_transfer(transfer, approver, approve, rejection_reason=""):
    item = Transfer.objects.select_for_update().select_related("employee").get(pk=transfer.pk)
    if item.status != Transfer.Status.PENDING:
        raise ValidationError("Đề nghị đã được xử lý.")
    if not approve and not rejection_reason.strip():
        raise ValidationError("Bắt buộc nhập lý do từ chối.")
    item.approver = approver
    if approve:
        item.status = Transfer.Status.APPROVED
        employee = item.employee
        employee.department = item.new_department
        employee.position = item.new_position
        employee.save(update_fields=["department", "position", "updated_at"])
    else:
        item.status = Transfer.Status.REJECTED
        item.rejection_reason = rejection_reason.strip()
    item.save()
    return item
