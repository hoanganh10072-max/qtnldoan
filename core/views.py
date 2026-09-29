import csv
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import admin_required, hr_required
from .forms import (
    AttendanceForm, CandidateConversionForm, CandidateForm, ContractForm,
    DepartmentForm, EmployeeForm, JobOpeningForm, LeaveRequestForm,
    PayrollAdjustmentForm, PayrollPeriodForm, PositionForm, RejectForm,
    TransferForm, UserForm,
)
from .models import (
    Attendance, Candidate, Contract, Department, Employee, JobOpening,
    LeaveRequest, Payroll, PayrollPeriod, Position, Transfer, User,
)
from .services import (
    approve_payroll_period, check_in, check_out, convert_candidate,
    create_transfer, decide_leave, decide_transfer, generate_payrolls,
)


def _page(request, queryset, size=15):
    from django.core.paginator import Paginator
    return Paginator(queryset, size).get_page(request.GET.get("page"))


def _employee_for(request):
    try:
        return request.user.employee
    except Employee.DoesNotExist as exc:
        raise PermissionDenied("Tài khoản chưa liên kết hồ sơ nhân viên.") from exc


def _form_page(request, form_class, *, instance=None, title="", success_url="dashboard"):
    form = form_class(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã lưu dữ liệu thành công.")
        return redirect(success_url)
    return render(request, "core/form.html", {"form": form, "title": title, "cancel_url": success_url})


@login_required
def dashboard(request):
    today = timezone.localdate()
    start_month = today.replace(day=1)
    if request.user.role == User.Role.EMPLOYEE:
        employee = _employee_for(request)
        latest_payroll = employee.payrolls.select_related("period").filter(period__status__in=[PayrollPeriod.Status.APPROVED, PayrollPeriod.Status.PAID]).order_by("-period__year", "-period__month").first()
        return render(request, "core/employee_dashboard.html", {
            "employee": employee,
            "attendance_count": employee.attendances.filter(work_date__gte=start_month, work_date__lte=today).count(),
            "pending_leave": employee.leave_requests.filter(status=LeaveRequest.Status.PENDING).count(),
            "latest_payroll": latest_payroll,
        })
    end_contract = today + timedelta(days=30)
    current_period = PayrollPeriod.objects.filter(month=today.month, year=today.year).first()
    stats = {
        "total": Employee.objects.count(),
        "active": Employee.objects.filter(status=Employee.Status.ACTIVE).count(),
        "new": Employee.objects.filter(hire_date__gte=start_month, hire_date__lte=today).count(),
        "resigned": Employee.objects.filter(status=Employee.Status.RESIGNED).count(),
        "pending_leave": LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).count(),
        "open_jobs": JobOpening.objects.filter(status=JobOpening.Status.OPEN).count(),
        "payroll_total": current_period.payrolls.aggregate(v=Sum("net_salary"))["v"] if current_period else 0,
        "expiring_contracts": Contract.objects.filter(status=Contract.Status.ACTIVE, end_date__range=(today, end_contract)).count(),
    }
    dept = list(Department.objects.annotate(total=Count("employees", filter=Q(employees__status=Employee.Status.ACTIVE))).values("name", "total"))
    gender = list(Employee.objects.filter(status=Employee.Status.ACTIVE).values("gender").annotate(total=Count("id")))
    statuses = list(Employee.objects.values("status").annotate(total=Count("id")))
    months, joined = [], []
    for offset in range(5, -1, -1):
        year = today.year if today.month - offset > 0 else today.year - 1
        month = (today.month - offset - 1) % 12 + 1
        months.append(f"{month:02d}/{year}")
        joined.append(Employee.objects.filter(hire_date__year=year, hire_date__month=month).count())
    salary_by_dept = list(Payroll.objects.filter(period=current_period).values("employee__department__name").annotate(total=Sum("net_salary"))) if current_period else []
    charts = {
        "department": {"labels": [x["name"] for x in dept], "values": [x["total"] for x in dept]},
        "gender": {"labels": [dict(Employee.Gender.choices).get(x["gender"], x["gender"]) for x in gender], "values": [x["total"] for x in gender]},
        "status": {"labels": [dict(Employee.Status.choices).get(x["status"], x["status"]) for x in statuses], "values": [x["total"] for x in statuses]},
        "movement": {"labels": months, "values": joined},
        "salary": {"labels": [x["employee__department__name"] for x in salary_by_dept], "values": [float(x["total"] or 0) for x in salary_by_dept]},
    }
    return render(request, "core/dashboard.html", {"stats": stats, "charts": charts})


@hr_required
def department_list(request):
    q = request.GET.get("q", "").strip()
    qs = Department.objects.select_related("manager")
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    return render(request, "core/object_list.html", {"title": "Phòng ban", "page_obj": _page(request, qs), "kind": "department", "add_url": "department_create", "q": q})


@hr_required
def department_detail(request, pk):
    obj = get_object_or_404(Department.objects.select_related("manager"), pk=pk)
    return render(request, "core/department_detail.html", {"object": obj, "employees": obj.employees.select_related("position")})


@hr_required
def department_create(request):
    return _form_page(request, DepartmentForm, title="Thêm phòng ban", success_url="department_list")


@hr_required
def department_update(request, pk):
    return _form_page(request, DepartmentForm, instance=get_object_or_404(Department, pk=pk), title="Chỉnh sửa phòng ban", success_url="department_list")


@admin_required
def department_delete(request, pk):
    obj = get_object_or_404(Department, pk=pk)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Đã xóa phòng ban.")
        except (ValidationError, IntegrityError) as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        return redirect("department_list")
    return render(request, "core/confirm.html", {"title": "Xóa phòng ban", "object": obj})


@hr_required
def position_list(request):
    q = request.GET.get("q", "").strip()
    qs = Position.objects.all()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    return render(request, "core/object_list.html", {"title": "Chức vụ", "page_obj": _page(request, qs), "kind": "position", "add_url": "position_create", "q": q})


@hr_required
def position_detail(request, pk):
    obj = get_object_or_404(Position, pk=pk)
    return render(request, "core/position_detail.html", {"object": obj, "employees": obj.employees.select_related("department")})


@hr_required
def position_create(request):
    return _form_page(request, PositionForm, title="Thêm chức vụ", success_url="position_list")


@hr_required
def position_update(request, pk):
    return _form_page(request, PositionForm, instance=get_object_or_404(Position, pk=pk), title="Chỉnh sửa chức vụ", success_url="position_list")


@admin_required
def position_delete(request, pk):
    obj = get_object_or_404(Position, pk=pk)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Đã xóa chức vụ.")
        except Exception:
            messages.error(request, "Không thể xóa chức vụ đang được sử dụng.")
        return redirect("position_list")
    return render(request, "core/confirm.html", {"title": "Xóa chức vụ", "object": obj})


@hr_required
def employee_list(request):
    qs = Employee.objects.select_related("department", "position", "user")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(employee_code__icontains=q) | Q(full_name__icontains=q))
    for key in ["department", "position", "status"]:
        value = request.GET.get(key)
        if value:
            qs = qs.filter(**{f"{key}_id" if key != "status" else key: value})
    return render(request, "core/employee_list.html", {
        "page_obj": _page(request, qs), "departments": Department.objects.all(), "positions": Position.objects.all(),
        "statuses": Employee.Status.choices, "filters": request.GET,
    })


@hr_required
def employee_create(request):
    return _form_page(request, EmployeeForm, title="Thêm nhân viên", success_url="employee_list")


@login_required
def employee_detail(request, pk):
    obj = get_object_or_404(Employee.objects.select_related("department", "position", "user"), pk=pk)
    if request.user.role == User.Role.EMPLOYEE and obj.user_id != request.user.id:
        raise PermissionDenied
    return render(request, "core/employee_detail.html", {"object": obj})


@hr_required
def employee_update(request, pk):
    return _form_page(request, EmployeeForm, instance=get_object_or_404(Employee, pk=pk), title="Chỉnh sửa nhân viên", success_url="employee_list")


@hr_required
def employee_resign(request, pk):
    obj = get_object_or_404(Employee, pk=pk)
    if request.method != "POST":
        raise Http404
    obj.status = Employee.Status.RESIGNED
    obj.save(update_fields=["status", "updated_at"])
    if obj.user:
        obj.user.is_active = False
        obj.user.save(update_fields=["is_active"])
    messages.success(request, "Đã chuyển nhân viên sang trạng thái nghỉ việc và khóa tài khoản.")
    return redirect("employee_detail", pk=pk)


@hr_required
def contract_list(request):
    qs = Contract.objects.select_related("employee")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(contract_number__icontains=q) | Q(employee__full_name__icontains=q))
    return render(request, "core/object_list.html", {"title": "Hợp đồng", "page_obj": _page(request, qs), "kind": "contract", "add_url": "contract_create", "q": q})


@hr_required
def contract_create(request):
    return _form_page(request, ContractForm, title="Thêm hợp đồng", success_url="contract_list")


@hr_required
def contract_update(request, pk):
    return _form_page(request, ContractForm, instance=get_object_or_404(Contract, pk=pk), title="Chỉnh sửa hợp đồng", success_url="contract_list")


@hr_required
def job_list(request):
    qs = JobOpening.objects.select_related("department").order_by("-created_at")
    return render(request, "core/object_list.html", {"title": "Vị trí tuyển dụng", "page_obj": _page(request, qs), "kind": "job", "add_url": "job_create"})


@hr_required
def job_create(request):
    return _form_page(request, JobOpeningForm, title="Thêm vị trí tuyển dụng", success_url="job_list")


@hr_required
def job_update(request, pk):
    return _form_page(request, JobOpeningForm, instance=get_object_or_404(JobOpening, pk=pk), title="Chỉnh sửa vị trí tuyển dụng", success_url="job_list")


@hr_required
def job_delete(request, pk):
    obj = get_object_or_404(JobOpening, pk=pk)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Đã xóa vị trí tuyển dụng.")
        except Exception:
            messages.error(request, "Không thể xóa vị trí đã có ứng viên; hãy chuyển sang trạng thái đã đóng.")
        return redirect("job_list")
    return render(request, "core/confirm.html", {"title": "Xóa vị trí tuyển dụng", "object": obj})


@hr_required
def candidate_list(request):
    qs = Candidate.objects.select_related("job_opening")
    q, status = request.GET.get("q", "").strip(), request.GET.get("status", "")
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q))
    if status:
        qs = qs.filter(status=status)
    return render(request, "core/object_list.html", {"title": "Ứng viên", "page_obj": _page(request, qs), "kind": "candidate", "add_url": "candidate_create", "q": q, "status_choices": Candidate.Status.choices})


@hr_required
def candidate_create(request):
    return _form_page(request, CandidateForm, title="Thêm ứng viên", success_url="candidate_list")


@hr_required
def candidate_update(request, pk):
    return _form_page(request, CandidateForm, instance=get_object_or_404(Candidate, pk=pk), title="Cập nhật ứng viên", success_url="candidate_list")


@hr_required
def candidate_convert(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)
    form = CandidateConversionForm(request.POST or None, initial={"hire_date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            employee = convert_candidate(candidate, form.cleaned_data)
            messages.success(request, f"Đã tiếp nhận {employee.full_name}, mã {employee.employee_code}.")
            return redirect("employee_detail", pk=employee.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "core/form.html", {"form": form, "title": f"Tiếp nhận ứng viên: {candidate.full_name}", "cancel_url": "candidate_list"})


@login_required
def attendance_list(request):
    qs = Attendance.objects.select_related("employee", "employee__department")
    if request.user.role == User.Role.EMPLOYEE:
        qs = qs.filter(employee=_employee_for(request))
    else:
        if request.GET.get("employee"):
            qs = qs.filter(employee_id=request.GET["employee"])
        if request.GET.get("department"):
            qs = qs.filter(employee__department_id=request.GET["department"])
    if request.GET.get("month"):
        try:
            year, month = map(int, request.GET["month"].split("-"))
            qs = qs.filter(work_date__year=year, work_date__month=month)
        except ValueError:
            pass
    return render(request, "core/attendance_list.html", {"page_obj": _page(request, qs), "employees": Employee.objects.filter(status=Employee.Status.ACTIVE), "departments": Department.objects.all()})


@login_required
def attendance_check_in(request):
    if request.method != "POST":
        raise Http404
    try:
        check_in(_employee_for(request))
        messages.success(request, "Chấm công vào thành công.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("attendance_list")


@login_required
def attendance_check_out(request):
    if request.method != "POST":
        raise Http404
    try:
        check_out(_employee_for(request))
        messages.success(request, "Chấm công ra thành công.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("attendance_list")


@hr_required
def attendance_create(request):
    return _form_page(request, AttendanceForm, title="Thêm/điều chỉnh chấm công", success_url="attendance_list")


@hr_required
def attendance_update(request, pk):
    return _form_page(request, AttendanceForm, instance=get_object_or_404(Attendance, pk=pk), title="Điều chỉnh chấm công", success_url="attendance_list")


@login_required
def leave_list(request):
    qs = LeaveRequest.objects.select_related("employee", "leave_type", "approver")
    if request.user.role == User.Role.EMPLOYEE:
        qs = qs.filter(employee=_employee_for(request))
    elif request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    return render(request, "core/leave_list.html", {"page_obj": _page(request, qs), "status_choices": LeaveRequest.Status.choices})


@login_required
def leave_create(request):
    employee = _employee_for(request)
    form = LeaveRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.employee = employee
        try:
            obj.save()
            messages.success(request, "Đã gửi đơn nghỉ phép.")
            return redirect("leave_list")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "core/form.html", {"form": form, "title": "Tạo đơn nghỉ phép", "cancel_url": "leave_list"})


@login_required
def leave_cancel(request, pk):
    obj = get_object_or_404(LeaveRequest, pk=pk, employee=_employee_for(request))
    if request.method != "POST" or obj.status != LeaveRequest.Status.PENDING:
        raise PermissionDenied
    obj.status = LeaveRequest.Status.CANCELLED
    obj.save(update_fields=["status", "updated_at"])
    messages.success(request, "Đã hủy đơn nghỉ phép.")
    return redirect("leave_list")


@hr_required
def leave_decide(request, pk, action):
    obj = get_object_or_404(LeaveRequest, pk=pk)
    form = RejectForm(request.POST or None) if action == "reject" else None
    if request.method == "POST" and (form is None or form.is_valid()):
        try:
            decide_leave(obj, request.user, action == "approve", form.cleaned_data["reason"] if form else "")
            messages.success(request, "Đã xử lý đơn nghỉ phép.")
            return redirect("leave_list")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("leave_list")
    if action == "approve":
        raise Http404
    return render(request, "core/form.html", {"form": form, "title": "Từ chối đơn nghỉ phép", "cancel_url": "leave_list"})


@hr_required
def payroll_period_list(request):
    return render(request, "core/payroll_period_list.html", {"page_obj": _page(request, PayrollPeriod.objects.annotate(total=Sum("payrolls__net_salary")).order_by("-year", "-month"))})


@hr_required
def payroll_period_create(request):
    return _form_page(request, PayrollPeriodForm, title="Tạo kỳ lương", success_url="payroll_period_list")


@hr_required
def payroll_period_detail(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    return render(request, "core/payroll_detail.html", {"period": period, "payrolls": period.payrolls.select_related("employee", "employee__department")})


@hr_required
def payroll_generate(request, pk):
    if request.method != "POST":
        raise Http404
    try:
        count = generate_payrolls(get_object_or_404(PayrollPeriod, pk=pk))
        messages.success(request, f"Đã tạo/cập nhật danh sách {count} bảng lương.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("payroll_period_detail", pk=pk)


@hr_required
def payroll_approve(request, pk):
    if request.method != "POST":
        raise Http404
    try:
        approve_payroll_period(get_object_or_404(PayrollPeriod, pk=pk), request.user)
        messages.success(request, "Đã duyệt và khóa kỳ lương.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("payroll_period_detail", pk=pk)


@hr_required
def payroll_mark_paid(request, pk):
    if request.method != "POST":
        raise Http404
    period = get_object_or_404(PayrollPeriod, pk=pk)
    if period.status != PayrollPeriod.Status.APPROVED:
        messages.error(request, "Chỉ kỳ lương đã duyệt mới được đánh dấu thanh toán.")
    else:
        period.status = PayrollPeriod.Status.PAID
        period.save(update_fields=["status", "updated_at"])
        messages.success(request, "Đã đánh dấu kỳ lương là đã thanh toán.")
    return redirect("payroll_period_detail", pk=pk)


@hr_required
def payroll_update(request, pk):
    obj = get_object_or_404(Payroll, pk=pk)
    return _payroll_form(request, obj)


def _payroll_form(request, obj):
    form = PayrollAdjustmentForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
            messages.success(request, "Đã tính lại lương.")
            return redirect("payroll_period_detail", pk=obj.period_id)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "core/form.html", {"form": form, "title": f"Điều chỉnh lương: {obj.employee.full_name}", "cancel_url": "payroll_period_list"})


@login_required
def payslip(request, pk):
    obj = get_object_or_404(Payroll.objects.select_related("employee__department", "employee__position", "period"), pk=pk)
    if request.user.role == User.Role.EMPLOYEE and obj.employee.user_id != request.user.id:
        raise PermissionDenied
    return render(request, "core/payslip.html", {"object": obj})


@login_required
def my_payslips(request):
    employee = _employee_for(request)
    return render(request, "core/my_payslips.html", {"page_obj": _page(request, employee.payrolls.select_related("period").filter(period__status__in=[PayrollPeriod.Status.APPROVED, PayrollPeriod.Status.PAID]))})


@hr_required
def transfer_list(request):
    return render(request, "core/transfer_list.html", {"page_obj": _page(request, Transfer.objects.select_related("employee", "old_department", "new_department", "old_position", "new_position"))})


@hr_required
def transfer_create(request):
    form = TransferForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        create_transfer(form.cleaned_data)
        messages.success(request, "Đã tạo đề nghị thuyên chuyển.")
        return redirect("transfer_list")
    return render(request, "core/form.html", {"form": form, "title": "Tạo đề nghị thuyên chuyển", "cancel_url": "transfer_list"})


@hr_required
def transfer_decide(request, pk, action):
    obj = get_object_or_404(Transfer, pk=pk)
    form = RejectForm(request.POST or None) if action == "reject" else None
    if request.method == "POST" and (form is None or form.is_valid()):
        try:
            decide_transfer(obj, request.user, action == "approve", form.cleaned_data["reason"] if form else "")
            messages.success(request, "Đã xử lý đề nghị thuyên chuyển.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("transfer_list")
    if action == "approve":
        raise Http404
    return render(request, "core/form.html", {"form": form, "title": "Từ chối thuyên chuyển", "cancel_url": "transfer_list"})


@admin_required
def user_list(request):
    return render(request, "core/object_list.html", {"title": "Tài khoản và phân quyền", "page_obj": _page(request, User.objects.order_by("username")), "kind": "user", "add_url": "user_create"})


@admin_required
def user_create(request):
    return _form_page(request, UserForm, title="Tạo tài khoản", success_url="user_list")


@admin_required
def user_update(request, pk):
    return _form_page(request, UserForm, instance=get_object_or_404(User, pk=pk), title="Cập nhật tài khoản", success_url="user_list")


@hr_required
def reports(request):
    today = timezone.localdate()
    return render(request, "core/reports.html", {
        "employee_count": Employee.objects.count(),
        "expiring": Contract.objects.filter(end_date__range=(today, today + timedelta(days=30))).select_related("employee")[:10],
        "pending_leaves": LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).count(),
        "open_jobs": JobOpening.objects.filter(status=JobOpening.Status.OPEN).count(),
        "transfers": Transfer.objects.count(),
    })


def _csv_response(filename, headers, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(rows)
    return response


@hr_required
def employee_csv(request):
    qs = Employee.objects.select_related("department", "position")
    return _csv_response("nhan-vien.csv", ["Mã", "Họ tên", "Email", "Phòng ban", "Chức vụ", "Trạng thái"], ((x.employee_code, x.full_name, x.email, x.department.name, x.position.name, x.get_status_display()) for x in qs))


@hr_required
def attendance_csv(request):
    qs = Attendance.objects.select_related("employee")
    return _csv_response("cham-cong.csv", ["Mã NV", "Họ tên", "Ngày", "Giờ vào", "Giờ ra", "Số giờ", "Trạng thái"], ((x.employee.employee_code, x.employee.full_name, x.work_date.strftime("%d/%m/%Y"), x.check_in or "", x.check_out or "", x.hours_worked, x.get_status_display()) for x in qs))


@hr_required
def payroll_csv(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    return _csv_response(f"bang-luong-{period.month:02d}-{period.year}.csv", ["Mã NV", "Họ tên", "Ngày công", "Lương cơ bản", "Phụ cấp", "Thưởng", "Khấu trừ", "Thực nhận"], ((x.employee.employee_code, x.employee.full_name, x.actual_days, x.base_salary, x.allowance, x.bonus, x.deduction, x.net_salary) for x in period.payrolls.select_related("employee")))


@hr_required
def report_csv(request, kind):
    if kind == "contracts":
        qs = Contract.objects.select_related("employee")
        return _csv_response("hop-dong.csv", ["Số HĐ", "Nhân viên", "Loại", "Bắt đầu", "Kết thúc", "Trạng thái"], ((x.contract_number, x.employee.full_name, x.get_contract_type_display(), x.start_date, x.end_date or "", x.get_status_display()) for x in qs))
    if kind == "recruitment":
        qs = Candidate.objects.select_related("job_opening")
        return _csv_response("tuyen-dung.csv", ["Ứng viên", "Email", "Điện thoại", "Vị trí", "Nguồn", "Trạng thái"], ((x.full_name, x.email, x.phone, x.job_opening.title, x.source, x.get_status_display()) for x in qs))
    if kind == "leaves":
        qs = LeaveRequest.objects.select_related("employee", "leave_type")
        return _csv_response("nghi-phep.csv", ["Nhân viên", "Loại", "Từ ngày", "Đến ngày", "Số ngày", "Trạng thái"], ((x.employee.full_name, x.leave_type.name, x.start_date, x.end_date, x.days, x.get_status_display()) for x in qs))
    if kind == "transfers":
        qs = Transfer.objects.select_related("employee", "old_department", "new_department")
        return _csv_response("thuyen-chuyen.csv", ["Nhân viên", "Phòng ban cũ", "Phòng ban mới", "Hiệu lực", "Trạng thái"], ((x.employee.full_name, x.old_department.name, x.new_department.name, x.effective_date, x.get_status_display()) for x in qs))
    raise Http404


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)
